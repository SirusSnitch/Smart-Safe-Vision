# streaming_utils.py
running_streams = set()

def should_start_stream(camera_id):
    if camera_id not in running_streams:
        running_streams.add(camera_id)
        return True
    return False

