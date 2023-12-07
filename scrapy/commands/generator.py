from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
import subprocess


# papago 번역 API 사용
import requests
import json

def setLanguage():
    text = "[Korean]: ko [English]: en [Japanese]:ja [Simplified Chinese]: zh-CN\n[Traditional Chinese]: zh-TW [Vietnamese]: vi [Indonesian]: id [Thai]: th\n[German]: de [Russian]: ru [Spanish]: es [Italian]: it\n[French]: fr\n"
    language = str(input(f"{text}Enter the language code you want to translate to: "))
    return language

def translate(text, language):

    # APP 등록 - access token
    CLIENT_ID, CLIENT_SECRET = "7Yw8ht8mnWqY2U1MEaaJ", "vCwi0FpefV"
    
    # request (en 외 언어로 번역도 가능)
    #text = "Error: Project names must begin with a letter and contain"+" only\nletters, numbers and underscores"
    url = 'https://openapi.naver.com/v1/papago/n2mt'
    headers = {
        'Content-Type': 'application/json',
        'X-Naver-Client-Id': CLIENT_ID,
        'X-Naver-Client-Secret': CLIENT_SECRET
    }
    data = {'source': 'en', 'target': language, 'text': text}
    
    # post 방식으로 서버 쪽으로 요청
    response = requests.post(url, json.dumps(data), headers=headers) 
    
    # json() 후 key 값을 사용하여 원하는 텍스트 접근
    after_text = response.json()['message']['result']['translatedText']
    return after_text

class Command(ScrapyCommand):
    requires_project = False
    default_settings = {"LOG_ENABLED": False}
    

    def syntax(self):
        return "[command]"

    def short_desc(self):
        return "Display help for Scrapy commands"

    def long_desc(self):
        return (
            "Display help for available Scrapy commands or detailed help for a "
            "specific command."
        )

    def run(self, args, opts):

        
        if args:
            command_name = args[0]
            # 처리할 특정 명령어가 입력되었을 때의 로직 추가
            if command_name == "start":
                isTranslate = input("Do you want to translate it?(y/n): ")
                while(True):
                    if isTranslate=="y":
                        self.generator_translate()
                        break
                    elif isTranslate=="n":
                        self.generator()
                        break
                    else:
                        print("Enter \'y\' or \'n\'")
                        isTranslate = input("Do you want to translate it?(y/n): ")
                
        else:
            # 모든 명령어에 대한 도움말 출력
            self.print_commands_help()

    def print_commands_help(self):
        # 여기에 사용 가능한 모든 명령어와 간단한 설명을 출력하는 로직 추가

        # 예: 간단한 설명 출력
        print("This is a command to help create a project")
        print("Easily create a project by entering the <scrapy generator start> command")
        # 추가 명령어에 대한 설명도 출력 가능

    def generator(self):
        print("\n=======================[default setting]=======================\n")

        while(True):
            # 프로젝트 생성
            project_name = input("Enter the name of the project: ")

            # 스파이더 이름 입력
            spider_name = input("Enter the name of the Spider: ")

            # 크롤링 주소 입력
            spider_url = input("Enter the website URL to crawl: ")

            # 템플릿 입력
            template_list = ["basic - This is the most fundamental spider template, containing all the essential elements required",
                                "crawl - Utilizes \'CrawlSpider\' for spiders\n Useful for crawling by following links",
                                "csvfeed - Utilizes CSV files for importing data",
                                "xmlfeed - Utilizes XML files for importing data"]
            print("\n============================[template list]============================\n")
            for i in range(len(template_list)):
                text = str(i+1)+". "+template_list[i]
                print(f"{text}")
            spider_template = input("\nEnter the template: ")

            print("\n============================[input check]============================\n")
            print(f"1. project name: {project_name}")
            print(f"2. Spider name: {spider_name}")
            print(f"3. URL to crwal: {spider_url}")
            print(f"4. template: {spider_template}")

            answer = input("\nIs the information you entered correct?(y/n): ")
            
            while(True):
                if  answer == "y":
                    print("\n================================[create process]================================\n")
                    # 입력받은 값 바탕으로 startproject 명령어 실행
                    subprocess.run(f'scrapy startproject {project_name}')
                    # 입력받은 값 바탕으로 genspider 명령어 실행
                    subprocess.run(f'scrapy genspider -t {spider_template} {spider_name} {spider_url}',cwd=f"{project_name}",shell=True)
                    break
                elif answer == "n":
                    break
                else:
                    print("Enter \'y\' or \'n\'")
                    answer = input("\nIs the information you entered correct?(y/n): ")

            if(answer=="y"):
                break
            else:
                continue
        
        print("\n====================================================================\n")

        while(True):
            isOpen = input("Do you want to open the created project in VSCode?(y/n): ")
            if isOpen == "y":
                subprocess.run("code .",cwd=f"{project_name}",shell=True)
                break
            elif isOpen =="n":
                isOpenExploler = input("Do you want to open the Project folder?(y/n): ")
                if isOpenExploler == "y":
                    subprocess.run("explorer .",cwd=f"{project_name}",shell=True)
                print("Ends the project creation")
                break
            else:
                print("Enter \'y\' or \'n\'")
    
    def generator_translate(self):
        language = setLanguage()
        print(translate("\n=======================[default setting]=======================\n",language))

        while(True):
            # 프로젝트 생성
            project_name = input(translate("Enter the name of the project:",language)+" ")

            # 스파이더 이름 입력
            spider_name = input(translate("Enter the name of the [Spider]:",language)+" ")

            # 크롤링 주소 입력
            spider_url = input(translate("Enter the website URL to crawl:",language)+" ")

            # 템플릿 입력
            template_list = ["basic - "+translate("This is the most fundamental [Spider] template, containing all the essential elements required",language),
                                "crawl - "+translate("Utilizes [CrawlSpider] for [Spiders]\n Useful for crawling by following links",language),
                                "csvfeed - "+translate("Utilizes CSV files for importing data",language),
                                "xmlfeed - "+translate("Utilizes XML files for importing data",language)]
            print(translate("\n============================[template list]============================\n",language))
            for i in range(len(template_list)):
                text = str(i+1)+". "+template_list[i]
                print(f"{text}")
            spider_template = input(translate("\nEnter the template:",language)+" ")

            print(translate("\n============================[input check]============================\n",language))
            print(translate("1. project name:",language),project_name)
            print(translate("2. [Spider] name:",language),spider_name)
            print(translate("3. URL to crwal:",language),spider_url)
            print(translate("4. template:",language),spider_template)

            answer = input(translate("\nIs the information you entered correct?(y/n):",language)+" ")
            
            while(True):
                if  answer == "y":
                    print(translate("\n================================[create process]================================\n",language))
                    # 입력받은 값 바탕으로 startproject 명령어 실행
                    subprocess.run(f'scrapy startproject {project_name}')
                    # 입력받은 값 바탕으로 genspider 명령어 실행
                    subprocess.run(f'scrapy genspider -t {spider_template} {spider_name} {spider_url}',cwd=f"{project_name}",shell=True)
                    break
                elif answer == "n":
                    break
                else:
                    print(translate("Enter \'y\' or \'n\'",language))
                    answer = input(translate("\nIs the information you entered correct?(y/n): ",language)+" ")

            if(answer=="y"):
                break
            else:
                continue

        print("\n====================================================================\n")

        while(True):
            isOpen = input(translate("Do you want to open the created project in VSCode?(y/n): ",language)+" ")
            if isOpen == "y":
                subprocess.run("code .",cwd=f"{project_name}",shell=True)
                break
            elif isOpen =="n":
                isOpenExploler = input(translate("Do you want to open the Project folder?(y/n): ",language))
                if isOpenExploler == "y":
                    subprocess.run("explorer .",cwd=f"{project_name}",shell=True)
                print(translate("Ends the project creation",language))
                break
            else:
                print(translate("Enter \'y\' or \'n\'",language))

                
        