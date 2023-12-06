from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError

class Command(ScrapyCommand):
    requires_project = False

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

            # 예: 특정 명령어에 대한 도움말 출력
            print(f"Help for '{command_name}' command...")
        else:
            # 모든 명령어에 대한 도움말 출력
            self.print_commands_help()

    def print_commands_help(self):
        print("Available Scrapy commands:")
        # 여기에 사용 가능한 모든 명령어와 간단한 설명을 출력하는 로직 추가

        # 예: 간단한 설명 출력
        print("프로젝트 생성을 돕기 위한 명령어 입니다")
        print("1. 프로젝트 이름 입력\n2. 생성할 스파이더 선택\n3. 스파이더 이름 입력\n4. 크롤링할 url 입력")
        # 추가 명령어에 대한 설명도 출력 가능

