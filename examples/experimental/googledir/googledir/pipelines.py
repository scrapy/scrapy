# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/topics/item-pipeline.html

from scrapy.core.exceptions import DropItem

class FilterWordsPipeline(object):
    """
    A pipeline for filtering out items which contain certain 
    words in their description
    """ 

    # put all words in lowercase
    words_to_filter = ['politics', 'religion']

    def process_item(self, spider, item):
        for word in self.words_to_filter:
            if word in unicode(item['description']).lower():
                raise DropItem("Contains forbidden word: %s" % word)
        else:
            return item
