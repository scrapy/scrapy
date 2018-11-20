import uuid
import os.path


def unique_files_queue(queue_class):

    class UniqueFilesQueue(queue_class):
        def __init__(self, path):
            path = path + "-" + uuid.uuid4().hex
            while os.path.exists(path):
                path = path + "-" + uuid.uuid4().hex

            super().__init__(path)

    return UniqueFilesQueue
