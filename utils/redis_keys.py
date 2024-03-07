
# string key:value pair that holds jsonified metadata on UUID peers
def get_snapshotter_info_key(alias):
    return f'snapshotterInfo:{alias}'


def get_last_message_sent_key(instance_id):
    return f'lastMessageSent:{instance_id}'