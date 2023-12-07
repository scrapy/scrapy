from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
import subprocess

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
                self.generator()
                
            # 예: 특정 명령어에 대한 도움말 출력
            # print(f"Help for '{command_name}' command...")
        else:
            # 모든 명령어에 대한 도움말 출력
            self.print_commands_help()

    def print_commands_help(self):
        # 여기에 사용 가능한 모든 명령어와 간단한 설명을 출력하는 로직 추가

        # 예: 간단한 설명 출력
        print("프로젝트 생성을 돕기 위한 명령어 입니다")
        print("<scrapy generator start> 명령어를 입력하여 손쉽게 프로젝트 구성을 시작하세요")
        # 추가 명령어에 대한 설명도 출력 가능

    def generator(self):
        print("\n=======================[기본 설정]=======================\n")

        while(True):
            # 프로젝트 생성
            project_name = input("프로젝트의 이름을 입력하세요: ")

            # 스파이더 이름 입력
            spider_name = input("스파이더의 이름을 입력하세요: ")

            # 크롤링 주소 입력
            spider_url = input("크롤링 할 url 주소를 입력하세요: ")

            # 템플릿 입력
            template_list = ["basic - 가장 기본적인 스파이더 템플릿. 모든 필수적인 요소들을 포함하고 있습니다",
                                "crawl - \'CrawlSpider\'를 사용하는 스파이더 템플릿입니다.\n           링크를 따라가며 크롤링하는 데 유용합니다",
                                "csvfeed - CSV 파일을 이용하여 데이터를 가져오는 템플릿입니다",
                                "xmlfeed - XML 파일을 이용하여 데이터를 가져오는 템플릿입니다"]
            print("\n============================[템플릿 목록]============================\n")
            for i in range(len(template_list)):
                text = str(i+1)+". "+template_list[i]
                print(f"{text}")
            spider_template = input("\n템플릿을 입력하세요: ")

            print("\n============================[입력 확인]============================\n")
            print(f"1. 프로젝트 이름: {project_name}")
            print(f"2. 스파이더 이름: {spider_name}")
            print(f"3. 크롤링할 주소: {spider_url}")
            print(f"4. 템플릿 선택: {spider_template}")

            answer = input("\n입력한 정보가 맞으십니까?(y/n): ")
            
            while(True):
                if  answer == "y":
                    print("\n================================[생성]================================\n")
                    # 입력받은 값 바탕으로 startproject 명령어 실행
                    subprocess.run(f'scrapy startproject {project_name}')
                    # 입력받은 값 바탕으로 genspider 명령어 실행
                    subprocess.run(f'scrapy genspider -t {spider_template} {spider_name} {spider_url}',cwd=f"{project_name}",shell=True)
                    break
                elif answer == "n":
                    break
                else:
                    print("\'y\' 또는 \'n\'를 입력하시오")
                    answer = input("\n입력한 정보가 맞으십니까?(y/n): ")

            if(answer=="y"):
                break
            else:
                continue
        
        while(True):
            isOpen = input("생성된 프로젝트를 vs code에서 여시겠습니까?(y/n): ")
            if isOpen == "y":
                subprocess.run("code .",cwd=f"{project_name}",shell=True)
                break
            elif isOpen =="n":
                print("프로젝트 생성을 종료합니다")
                break
            else:
                print("\'y\' 또는 \'n\'를 입력하시오")

                
        