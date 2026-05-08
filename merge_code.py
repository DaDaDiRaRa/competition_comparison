import os

# 1. 설정: 검색할 폴더 경로와 포함/제외할 확장자 및 폴더 지정
TARGET_DIRECTORY = '.'  # 현재 폴더를 기준으로 실행
OUTPUT_FILE = 'merged_code.txt' # 결과물이 저장될 파일 이름

# AI에게 보여줄 필요가 없는 무거운 폴더나 설정 폴더들
EXCLUDE_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', 'build', 'dist', 'public'}
# 추출하고 싶은 소스 코드 확장자 (사용하시는 언어에 맞게 수정하세요)
INCLUDE_EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.md'}

def merge_code_files(start_path, output_path):
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # os.walk를 사용하여 디렉토리 트리를 순회합니다.
        for root, dirs, files in os.walk(start_path):
            # 제외할 폴더는 순회 목록에서 제거하여 탐색 속도를 높입니다.
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            for file in files:
                # 파일의 확장자를 확인합니다.
                _, ext = os.path.splitext(file)
                if ext in INCLUDE_EXTENSIONS:
                    file_path = os.path.join(root, file)
                    
                    try:
                        # 2. 코드 파일 읽기 및 포맷팅
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            
                            # AI가 파일 구조를 이해하기 쉽도록 구분자를 추가합니다.
                            outfile.write(f"\n\n{'='*50}\n")
                            outfile.write(f"File: {file_path}\n")
                            outfile.write(f"{'='*50}\n\n")
                            outfile.write(content)
                            
                    except Exception as e:
                        print(f"파일을 읽는 중 오류 발생 ({file_path}): {e}")

if __name__ == "__main__":
    print("소스 코드를 추출하여 병합 중입니다...")
    merge_code_files(TARGET_DIRECTORY, OUTPUT_FILE)
    print(f"완료되었습니다! '{OUTPUT_FILE}' 파일을 확인해주세요.")