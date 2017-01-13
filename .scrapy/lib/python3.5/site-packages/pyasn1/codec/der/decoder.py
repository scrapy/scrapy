# DER decoder
from pyasn1.codec.cer import decoder

tagMap = decoder.tagMap
typeMap = decoder.typeMap
class Decoder(decoder.Decoder):
    supportIndefLength = False

decode = Decoder(tagMap, typeMap)
