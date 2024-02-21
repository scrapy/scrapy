# Report for assignment 3

## Project

Name: Scrapy

URL: https://github.com/roxannecvl/scrapy/tree/master

We forked the Scrapy open source project which is a web scraper to perform
assignment 3 on.

## Onboarding experience

We started off with Pyspider which made use of a requirements.txt to
document the dependencies which Python has tools to download automatically.
Running the tests however, we discovered that somethings had been deprecated
meaning a major overhaul would be required to get the code running and we
therefore swapped project.

Scrapy's README.md itself didn't have that much documentation. You instead
have to navigate to their website which includes a bunch of documentation on
running, testing, how to contribute etc. Since the project is fairly large,
the setup process which uses a setup.py takes quite a bit of time. Running
the test suite also takes upwards of 10 minutes.

## Complexity

The function I am going to be looking at is _get_form in 
scrapy/http/request/form.py. Using the lizard tool, it assigns
the function a value of 12 CCN and an NLOC of 37. A manual count by
counting the decision points and adding 1 gives us a CCN of 12. Using
the calculation method from the lecture we instead get Number of
Decisions = 11, Exit Points = 7, totalling 11-7+2=6.

The purpose of the function is to find a form in an HTTP request.
There is not much documentation on this function since the convention
in Python is that functions starting with an underscore is supposed to
be Private, meaning it is only invoked within the class by another
function. The function is moderately convoluted and long because of
all the nested if-statements and all the exceptions that needs to
be taken into account.

The function that I am going to peer review in regards to Cyclomatic
Complexity Number is strip_url in scrapy/utils/url.py. Lizard gives
it a CCN of 12 and my manual count also leads to 12 assuming
counting the amount of decision points + 1 as well as the logical
operators 'or' and 'and' within the if statements.
 
## Refactoring

To refactor _get_form would be a moderately difficult task as
the if statements contributing to its high complexity is
necessary for its function to extract values from a HTTP
file that can look in many different ways. As the function
can be seen as having 4-5 major if-statements that successively
goes deeper and deeper into the HTML file, one could break out
those into separate functions. The impact would be more readable
_get_form since you have abstracted those if-statements into
much fewer lines as a function call. Other than the impact
on readability, a potential drawback is that you clutter the
class with more functions that only serve the purpose of being
used in the _get_form function, making the file more convoluted
when looking at it from a high level. It becomes a trade-off
between readability of the individual function or the readability
of the whole class.

## Coverage

### Tools

The coverage on the original Scrapy repo leads to this, and looking
up my function, it is mostly covered with a small gap which
we will address with an extra test case.
https://app.codecov.io/github/scrapy/scrapy/blob/master/scrapy%2Fhttp%2Frequest%2Fform.py

Using GitHub:s code indexing, we can see that _get_form is invoked once
from from_response in the same class. Looking for the relevant invocations
of this function, we find 64 calls all within tests/test_http_request.py
meaning we can cut down the test suite considerably when focusing on this
function alone.

Running this singular test file yields that 177 tests passed.

Using Coverage.py at first was tricky, I ran the test file with
coverage run -m unittest test_http_request.py and the report only
yielded the coverage of the test file itself. After some troubleshooting
the problem was that I didn't run the command from the root of the
repository, so I changed my location and command to
coverage run -m unittest tests/test_http_request.py.

I then generated coverage html and checked the function that I am interested
in. What I found is that most things is indeed covered at 96%. As for
the function I am interested in, there is 1 decision path that is not
covered.


### Your own coverage tool

I took the simple approach to manual instrumentation of my function by
creating an array and hardcoding in the function the different branches
if they are accessed with the array. At the end of the test class,
the array will be printed and thereby showing whether all branches
have been taken or not. Also added else clauses to the if without to
make sure that the path of the if clause being skipped exists.

In the test file, after all the tests have been ran, I run the function
that prints out this global array of what parts of the function have
been run, and the results correspond with the Lizard results
where one of the clauses did not get run.

### Evaluation

The coverage measurement is hard-coded and crude and you have to manually locate
the corresponding line of code that has not been run from the terminal output.
One limitation to this approach is that if there are multiple test classes that
use this function, another approach would be required to assimilate the multiple
results since this approach relies on the class object staying persistent between
tests. The results of this tool is the same as the proper coverage tool, i.e.
I was able to locate the same clause that has not been run.

## Coverage improvement

The coverage for the class file I was working with was 96%, there
were 2 clauses unaccounted for in 2 different functions.

I added a test case for _get_inputs since there was one exception
that was not covered.

I added a test case for _get_form since there was one unused line
of code where one kind of input wasn't taken into account.

After adding these tests, the coverage report showed 99% and the
expected result of the 2 missing clauses now actually being
covered shows on the report as well as the manual instrumentation tool.

## Self-assessment: Way of working

Current state according to the Essence standard: ...

Was the self-assessment unanimous? Any doubts about certain items?

How have you improved so far?

Where is potential for improvement?

## Overall experience

What are your main take-aways from this project? What did you learn?

Is there something special you want to mention here?