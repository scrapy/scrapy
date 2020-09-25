====================================================
Custom Amazon S3 headers in FileStorage
====================================================

Steps to pass **SSEKMSKeyId** and **ServerSideEncryption** to **scrapy** FilesPipeline using **AWS S3**


Configuration Steps
======================

1. Subclass ``scrapy.pipelines.files.S3FilesStore``, 

2. Extend its ``HEADERS`` class attribute in your subclass to define the headers you want with the values you 
   want,

3. In your case, the corresponding headers are: ``X-Amz-Server-Side-Encryption``, 
   ``X-Amz-Server-Side-Encryption-Aws-Kms-Key-Id``

4. You can see the header-to-key mapping in the source code of the class, for additional header names,

5. Subclass ``FilesPipeline``, and edit the ``STORE_SCHEMES`` class attribute in your subclass to point ``s3`` 
   to your ``S3FilesStore`` subclass,

6. Update your ``ITEM_PIPELINES`` setting to use your ``FilesPipeline`` subclass.