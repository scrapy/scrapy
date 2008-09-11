from traceback import format_exc

class AdaptorPipe:

    def __init__(self, adaptors_dict=None):
        """
        Receives a dictionary that maps attribute_name to a list of adaptor functions
        """
        self.pipes = adaptors_dict or {}

    def execute(self, attrname, value, debug=False):
        """
        Execute pipeline for attribute name "attrname" and value "value".
        """
        for function in self.pipes.get(attrname, []):
            try:
                if debug:
                    print "  %07s | input >" % function.func_name, repr(value)
                value = function(value)
                if debug:
                    print "  %07s | output>" % function.func_name, repr(value)

            except Exception, e:
                print "Error in '%s' adaptor. Traceback text:" % function.func_name
                print format_exc()
                return

        return value
