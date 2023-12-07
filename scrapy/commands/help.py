from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError

        

class Command(ScrapyCommand):
    requires_project = False
    default_settings = {"LOG_ENABLED": False}
    
    def print_commands_help(self):
        print("=====도움말 명령어 목록=====")
        print("<startproject, genspider, crawl, list, fetch, generator>")
        print("다음 명령어 중 하나를 입력하여 도움말을 확인하세요.")
        
    def startproject_commands_help(self):
        print("<scrapy startproject 프로젝트이름> 명령어를 입력하여 프로젝트를 생성하세요.")
    
    def genspider_commands_help(self):
        print("<scrapy genspider 스파이더이름 도메인> 명령어를 입력하여 도메인에서 데이터를 크롤링할 스파이더를 생성하세요.")
        
    def crawl_commands_help(self):
        print("<scrapy crawl 스파이더이름> 명령어를 입력하여 지정된 스파이더를 실행하여 웹 페이지를 크롤링하세요.")
        print("명령어 뒤에 추가적인 입력을 통해 옵션을 사용할 수 있습니다.")
        print("-o <file> : 크롤링 결과를 파일로 저장합니다.\n-t <format> : 출력 파일의 형식을 지정합니다.")
        print("-a <key=value> : 스파이더에게 인수를 전달합니다.")
        
    def list_commands_help(self):
        print("<scrapy list> 명령어를 통해 현재 프로젝트에 있는 사용 가능한 스파이더 목록을 확인하세요.")
        
    def fetch_commands_help(self):
        print("<scrapy fetch 웹페이지주소(URL)> 명령어를 통해 크롤링할 웹페이지 구조, 내용을 미리 확인하세요.")
     
    def generator_commands_help(self):
        print("프로젝트 생성을 돕기 위한 명령어 입니다.")
        print("<scrapy generator start> 명령어를 입력하여 손쉽게 프로젝트 구성을 시작하세요.")   
    

    
        
    #명령어별로 도움말을 저장할 딕셔너리
    helpCommandDict = {'startproject' : startproject_commands_help, 'genspider' : genspider_commands_help, 'crawl' : crawl_commands_help,
                       'list' : list_commands_help,  'fetch' : fetch_commands_help, 'generator': generator_commands_help}
    
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
            
            if command_name in self.helpCommandDict:
                self.helpCommandDict[command_name](self)
            else:
                print("잘못 입력하셨습니다.\n도움이 필요한 명령어를 다시 입력하세요.")
                
        else:
            # 모든 명령어에 대한 도움말 출력
            self.print_commands_help()

   
