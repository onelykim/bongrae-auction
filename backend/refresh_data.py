"""
데이터 스냅샷을 한 번 갱신하고 종료하는 CLI.

서버 내장 스케줄러 대신 '외부 크론'이나 'GitHub Actions'로 매일 돌릴 때 사용.
    python refresh_data.py

환경변수 ONBID_SERVICE_KEY / MOLIT_SERVICE_KEY 를 함께 넣으면 실데이터로 갱신.
결과는 ../data/snapshot.json 에 저장되어, 서버가 다음 요청부터 즉시 사용합니다.
"""
import dataset

if __name__ == "__main__":
    meta = dataset.refresh()
    print("갱신 결과:", meta)
