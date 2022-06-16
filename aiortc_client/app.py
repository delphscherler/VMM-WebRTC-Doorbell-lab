# Loop forever:
#   1. Wait until keypress (to be replaced later by the pushbutton press event).
#   2. Connect to the signaling server.
#   3. Join a conference room with a random name (send 'create' signal with room name).
#   4. Wait for response. If response is 'joined' or 'full', stop processing and return to the loop. Go on if response is 'created'.
#   5. Send a message (SMS, Telegram, email, ...) to the user with the room name. Or simply start by printing it on the terminal. 
#   6. Wait (with timeout) for a 'new_peer' message. If timeout, send 'bye' to signaling server and return to the loop. 
#   7. Wait (with timeout) for an 'invite' message. If timemout, send 'bye to signaling server and return to the loop. 
#   8. Acquire the media stream from the Webcam.
#   9. Create the PeerConnection and add the streams from the local Webcam.
#   10. Add the SDP from the 'invite' to the peer connection.
#   11. Generate the local session description (answer) and send it as 'ok' to the signaling server.
#   12. Wait (with timeout) for a 'bye' message. 
#   13. Send a 'bye' message back and clean everything up (peerconnection, media, signaling).

import socketio
import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaRecorder, MediaStreamTrack

room_name = "room"
messages = ['created', 'joined', 'full', 'new_peer', 'invite', 'bye']
timeout = 20

def create_queue(sio: socketio.AsyncClient):
    queue = asyncio.Queue()
    for msg in messages:
        sio.on(msg, put_message(queue, msg))
    return queue

def put_message(queue: asyncio.Queue, type: str):
    def inside(msg):
        queue.put_nowait((type, msg))
    return inside

async def main():
    while True :
        # 1. Wait until keypress
        input("Press any key to continue...")

        # 2. Connecting to the signaling server
        sio = socketio.AsyncClient(ssl_verify=False)
        await sio.connect('https://10.192.95.102:443')

        # 3. Join a conference room
        await sio.emit('join', room_name)

        # 4. Wait for response.
        queue = create_queue(sio)
        msg = await asyncio.wait_for(queue.get(), None)
        if msg[0] == 'joined' or msg[0] == 'full':           
            return

        # 5. Send a message
        print(f"Please join room '{msg[1]}'")
        
        # 6. wait for message 'new_peer'
        msg = await asyncio.wait_for(queue.get(), timeout)
        if msg[0] != 'new_peer':
            await sio.emit('bye')
            return

        # 7. wait for message 'invite'
        msg = await asyncio.wait_for(queue.get(), timeout)
        if msg[0] != 'invite':
            await sio.emit('bye')
            return

        # 8. Acquire the media stream +
        # 9. Create the PeerConnection and add the streams from the local Webcam.
        configuration = RTCConfiguration([RTCIceServer('stun:stun.l.google.com:19302')])
        pc = RTCPeerConnection(configuration)
        playerVideo = MediaPlayer('/dev/video0', format = 'v4l2', options = { 'video_size': '320x240' })
        pc.addTrack(playerVideo.video)
        playerAudio = MediaPlayer('default', format = 'pulse')
        pc.addTrack(playerAudio.audio)

        recorder = MediaRecorder('default', format = 'alsa')
        @pc.on('track')
        def on_track(track: MediaStreamTrack):
            recorder.addTrack(track)

        await recorder.start()

        # 10. Add the SDP from the 'invite' to the peer connection.
        offer = msg[1]
        await pc.setRemoteDescription(RTCSessionDescription(offer['sdp'], offer['type']))
        # 11. Generate the local session description (answer) and send it as 'ok' to the signaling server.
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        answer = pc.localDescription
        await sio.emit('ok', {'sdp': answer.sdp, 'type': answer.type})
        # 12. Wait (with timeout) for a 'bye' message.
        try:
            msg = await asyncio.wait_for(queue.get(), timeout)
            if msg[0] == 'bye':
                # 13. Send a 'bye' message back and clean everything up (peerconnection, media, signaling).
                await sio.emit('bye', room_name)
                await sio.disconnect()
                await recorder.stop()
                playerVideo.video.stop()
                del playerVideo
                playerAudio.audio.stop()
                del playerAudio
                await pc.close()
                pc = None
        except asyncio.TimeoutError:
            print("no bye")

asyncio.run(main())

