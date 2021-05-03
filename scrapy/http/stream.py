# class DummyBodyStream:
#     def __init__(self):
#         self.limit = 5
#         self.current = 0

#     def __aiter__(self):
#         return self

#     async def __anext__(self):
#         if self.current >= self.limit:
#             raise StopAsyncIteration
#         self.current = self.current + 1
#         return self.current


# class BodyStream:
#     def __init__(self, protocol):
#         self.protocol = protocol
#         self.limit = 5
#         self.current = 0

#     def __aiter__(self):
#         return self

#     async def __anext__(self):
#         if self.current >= self.limit:
#             raise StopAsyncIteration
#         self.current = self.current + 1
#         return self.current
