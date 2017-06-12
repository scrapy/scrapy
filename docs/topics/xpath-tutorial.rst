==============
XPath Tutorial
==============

Welcome to the xpath tutorial. Have a look at this expression:

.. xpathdemo:: //h2/a

    <html>
        <head>
            <title>My page</title>
        </head>
        <body>
            <h2>Welcome to my <a href="#">page</a></h2>
            <p>This is the first paragraph</p>.
            <!-- this is the end -->
        </body>
    </html>

And this one :-) :

.. xpathdemo:: //h2

    <html>
      <h2>Welcome to my <a href="#">page</a></h2>
      <p>This is the first paragraph</p>.
      <!-- this is the end -->
    </html>
