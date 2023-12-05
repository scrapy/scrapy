# careful: whitespace is very important in this file
# also, this code runs - so everything should be a noop

class BlankLineBetweenMethods:
    def method1(self):
        pass

    def method2(self):
        pass

def BlankLineInFunction(self):
    return 7

    pass

#StartTest-blank_lines_in_for_loop
for i in range(2):
    pass

    pass
#EndTest

#StartTest-blank_line_in_try_catch
try:
    1

except:
    2
#EndTest

#StartTest-blank_line_in_try_catch_else
try:
    1

except:
    2

else:
    3
#EndTest

#StartTest-blank_trailing_line
def foo():
    return 1

#EndTest

def tabs():
	return 1
