"""강남구 관광 데이터 학습을 실행하는 간단한 프로그램입니다.

실행 방법:
    python -m ai_server.ml.train_gangnam_014

이 파일은 학습 방법을 새로 만들지 않습니다.
기존의 train_gangnam_models()를 그대로 호출하므로
모델, 데이터, 평가 방법은 기존 train_gangnam.py와 같습니다.
"""
# train_gangnam_014.py 에서 수정 
# 초보자 수준의 코드로 수정한 파일


from __future__ import annotations

import json

from .gangnam_forecast import train_gangnam_models


def make_summary(metadata: dict) -> dict:
    """학습 결과에서 콘솔에 보여 줄 내용만 골라냅니다."""

    print('make_summary 함수 내부\n')
    print(metadata,'\n')
    targets = {}

    # 학습한 관광 지표를 하나씩 확인합니다.
    for target_name in metadata["target"]:

        print(target_name,'\n')
        result = metadata["evaluation"][target_name]
        print('metadata["evaluation"][target_name] :',result)



        targets[target_name] = {
            "selected_model": result["selected_model"],
            "test_mape_percent": result["selected_model_metrics"]["mape_percent"],
            "baseline_test_mape_percent": result["baseline_metrics"]["mape_percent"],
            "beats_baseline_on_test": result["beats_baseline_on_test"],
        }

        print("""targets[target_name] = {
                "selected_model": result["selected_model"], 
                "test_mape_percent": result["selected_model_metrics"]["mape_percent"], 
                "baseline_test_mape_percent": result["baseline_metrics"]["mape_percent"], 
                "beats_baseline_on_test": result["beats_baseline_on_test"], 
            }""")
        print('targets[target_name] :' ,targets[target_name])
        


    print("""
            "model_version": metadata["version"],
            "source_period": metadata["source_period"],
            "test_period": metadata["test_period"],
            "targets": targets,
                }""")
    print('metadata["version"]:',metadata["version"])
    print('metadata["source_period"]:',metadata["source_period"])
    print('metadata["test_period"]:',metadata["test_period"])
    print('targets:',targets)

    print( "make_summary 종료")          

    return {
        "model_version": metadata["version"],
        "source_period": metadata["source_period"],
        "test_period": metadata["test_period"],
        "targets": targets,
    }


def main() -> None:
    """모델을 학습하고 평가 결과를 JSON으로 출력합니다."""
    print("강남구 모델 학습을 시작합니다.")

    # 실제 학습과 모델 파일 저장은 기존 함수가 담당합니다.
    print("#### 2 train_gangnam_models 호출")
    metadata = train_gangnam_models()

    # 전체 메타데이터 대신 확인에 필요한 요약만 출력합니다.
    print('#### 3 make_summary')
    summary = make_summary(metadata)

    print("파이썬 객체를 json으로 저장")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":

    print('#### 1')
    print()

    main()


### 
# 실행방법 : python -m ai_server.ml.train_gangnam_014
# 
# 실행하기
#  .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam    

# print한 내용 저장하기 
# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam `
#    > ".\training_result.txt" 2>&1

# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam `
#   > ".\ai_server\ml\training_result.txt" 2>&1


# >와 2>&1의 의미
# > ".\ai_server\ml\training_result.txt" 2>&1

# 여기서

# > : print() 등의 표준 출력(stdout) 을 파일로 저장
# 2> : 오류 출력(stderr) 을 지정
# 2>&1 : 오류 출력도 표준 출력과 같은 곳으로 보냄

# 따라서 학습 중 나오는

# 강남구 모델 학습을 시작합니다.
# #### 2 train_gangnam_models 호출
# ...

# 뿐만 아니라 오류 메시지도 training_result.txt에 함께 저장됩니다.

# 기존 파일에 계속 추가하고 싶다면

# 현재 >는 기존 파일을 새로 덮어씁니다.

# 기존 내용 뒤에 계속 추가하려면 >>를 사용합니다.

# cd .\backend

# & ".\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_000-1 `
#   >> ".\ai_server\ml\training_result.txt" 2>&1

# 추천은 >입니다. 학습을 새로 실행할 때마다 이전 결과를 지우고 새로운 결과만 저장하기 때문에 모델 학습 결과를 확인하기 편합니다.