from scrapy.selector import Selector

class DBpediaAccess:

#     The following method opens a DBpedia page url and returns
#     the label of an entity or an attribute as a list
#     :elements1: the list of labels

    def getLiterals(self, url):
        from scrapy.selector import Selector
        from scrapy.http import HtmlResponse
        from urllib.request import urlopen
        try:
            with urlopen(url) as response:

                    html_response = response.read()
                    encoding = response.headers.get_content_charset('utf-8')
                    decoded_html = html_response.decode(encoding)
                    sel = Selector(text=decoded_html)
                    elements1 = sel.xpath('//span[contains(@property,"rdfs:label")]/text()').getall()
        except:
            elements1 = [url]
        if len(elements1) > 0:
            return elements1


#     The following function is to extract data from a DBPedia page
#     and return those data in a pdf version. The page's url is given as a
#     parameter in order to decode its source code. Regarding the appearance 
#     of the data, they are structured in a two-column table where in the left 
#     side there are all the properties and in the right side their corresponding
#     values. Caution has to be taken in the case that a value has the data type 
#     Text and it can be displayed in different languages. After the data are 
#     checked and stored temporarily, the pdf is designed and filled line by line 
#     with our saved information.
#     : url: url from dbpedia
#     : pdf: if it is true, the result will be printed in a pdf file
#     : pdffilename: the filename of the generated pdf file
#     : sep: the fields' separator 

    def getContentFromDBPedia(self, url, pdf=False, pdffilename="nopdf", sep=' '):
        from scrapy.selector import Selector
        from scrapy.http import HtmlResponse
        from urllib.request import urlopen

        try:
            with urlopen(url) as response:
                html_response = response.read()
                encoding = response.headers.get_content_charset('utf-8')
                decoded_html = html_response.decode(encoding)
        except:
            return "URL ERROR"
        try:
            sel = Selector(text=decoded_html)

            #save all the properties (left side of the table)
            elements1 = sel.css("td.col-2 a::attr(href)").getall()

            #save all the values (right side of the table)
            elements2 = sel.xpath('//td[contains(@class, "col-10")]')
        except:
            return "Scrapping Error"

        if len(elements1) != len(elements2) or len(elements1)==0:
                return "Content scrapped is invalid"

    #save each entity/attribute with its corresponding value
        try:
            content = []
            for index, link in enumerate(elements2):
                href_xpath = link.css('span[lang*=en] *::text').get()
                if href_xpath == None:
                    href_xpath = link.css('span *::text').getall()
                    href_xpath = sep.join(href_xpath)
                content.append(href_xpath)
            lines = []
            for e in range(0,len(elements1)):

            #check if a value has the data type Text and it 
            #can be displayed in different languages. In this case,
            #seperate the multiple tests based on the separator which is
            #given as a parameter

                line = (self.getLiterals(elements1[e]),content[e])
                lines.append(line)
        except:
            return "Scrapping Error"
    #create a pdf
        if pdf==True:
            try:
                from reportlab.pdfgen.canvas import Canvas
                from reportlab.lib.colors import blue
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.units import inch
                from reportlab.pdfgen.canvas import Canvas
                import textwrap
                canvas = Canvas(pdffilename, pagesize=A4)
                canvas.setFont("Times-Roman", 12)

                wrapper = textwrap.TextWrapper(width=90)

                L = 1
                for entry in lines:
                    if (str(type(entry[0]))=="list"):
                        entr = '/'.join(map(str,entry[0]))
                    elif (str(type(entry[0]))=="str"):
                        entr = entry[0];
                    else:
                        entr = str(entry[0])
                    pdfstring = entr +" : "+entry[1]

                    if len(pdfstring)>80:
                        word_list = wrapper.wrap(text=pdfstring)
                        for sl in word_list:
                            if L % 30 == 0:
                                canvas.showPage()
                                L = 1
                            canvas.drawString(1 * inch, 10 * inch - 0.25 * L * inch, sl)
                            L = L + 1
                    else:
                            if L % 30 == 0:
                                canvas.showPage()
                                L = 1
                            canvas.drawString(1 * inch, 10 * inch - 0.25 * L * inch, pdfstring)
                            L = L + 1

            # Save the PDF file
                canvas.save()
                return "Result saved to pdf file"
            except:
                return "Could not create pdf file"
        else:
            return lines  

