class Cancelled(Exception):
    pass

def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled('処理を中止しました')
