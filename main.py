import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
import logging
import re

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# QT 웹사이트 URL
QT_URL = "https://sum.su.or.kr:8888/bible/today"

async def fetch_qt_data():
    """
    매일성경(sum.su.or.kr)에서 오늘의 QT 내용을 크롤링합니다.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(QT_URL)
            response.raise_for_status() # 4xx, 5xx 에러 발생 시 예외 처리
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 날짜 및 제목 추출
        # 사이트 구조에 따라 선택자가 달라질 수 있으므로 예외처리 주의
        title_element = soup.select_one("#bible_text") 
        sub_title_element = soup.select_one("#bibleinfo_box") 
        
        # 제목 정제 (예: 2025.04.18(금) 제목...)
        title_text = title_element.get_text(strip=True) if title_element else "제목 없음"
        bible_ref = sub_title_element.get_text(strip=True) if sub_title_element else "본문 정보 없음"

        # 2. 본문 텍스트 (본문이 여러 구절일 수 있음)
        body_text_element = soup.select_one("#body_list")
        bible_text = body_text_element.get_text(separator="\n", strip=True) if body_text_element else "본문을 불러올 수 없습니다."
        
        # 3. 찬송 (보통 하단이나 별도 영역에 위치)
        # sum.su.or.kr 구조상 찬송가는 별도 파싱이 까다로울 수 있어, 텍스트 내에서 찾거나 고정값 처리 필요할 수 있음
        # 여기서는 예시로 'bibleinfo_box' 근처나 본문 하단을 찾습니다.
        # (구조가 불명확할 경우 안전하게 생략하거나 빈값 처리)
        song_text = "-" 

        # 4. 해설 (commentary)
        # 매일성경 사이트는 탭으로 구분되어 있어 추가 요청이 필요할 수 있으나, 
        # 기본 페이지에 포함된 경우 파싱 시도.
        # (만약 iframe이나 별도 호출이라면 이 부분은 수정 필요)
        commentary_element = soup.select_one("#commentary_view") # 가상의 선택자 (실제 사이트 구조 확인 후 수정 가능)
        commentary_text = ""
        if commentary_element:
            commentary_text = commentary_element.get_text(separator="\n", strip=True)
        else:
            # 해설을 못 찾았을 경우 간단한 안내
            commentary_text = "해설은 웹사이트에서 확인해주세요."

        return {
            "title": title_text,
            "bible_ref": bible_ref,
            "bible_text": bible_text,
            "song": song_text,
            "commentary": commentary_text,
            "url": QT_URL
        }

    except Exception as e:
        logger.error(f"QT 크롤링 실패: {str(e)}")
        return None

@app.post("/qt")
async def get_qt(request: Request):
    """
    카카오톡 스킬 서버 엔드포인트
    """
    qt_data = await fetch_qt_data()

    if not qt_data:
        # 크롤링 실패 시 에러 메시지 응답
        return JSONResponse(content={
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": "죄송합니다. 큐티 정보를 가져오는데 실패했습니다.\n잠시 후 다시 시도해주세요."
                        }
                    }
                ]
            }
        })

    # --- 카카오톡 응답 생성 (말풍선 3개 구조) ---
    
    # 1. 첫 번째 말풍선: 제목, 본문, 찬송
    # 텍스트 길이 제한(1000자)을 고려하여 적절히 자릅니다.
    main_msg = f"✝오늘의 QT✝\n\n[{qt_data['title']}]\n본문: {qt_data['bible_ref']}\n\n{qt_data['bible_text'][:800]}"
    if len(qt_data['bible_text']) > 800:
        main_msg += "..."

    # 2. 두 번째 말풍선: 해설 (텍스트 양이 많을 수 있으므로 분리)
    commentary_msg = f"📖 오늘의 묵상\n\n{qt_data['commentary'][:900]}"
    if len(qt_data['commentary']) > 900:
        commentary_msg += "...\n(전체 내용은 링크 참조)"

    # 3. 세 번째 말풍선: 하단 링크 및 격려 메시지
    footer_msg = f"🔗 해설 전문 보기: {qt_data['url']}\n\n🌟아침에 말씀으로 시작하며 하나님의 은혜 충만으로 하루를 시작해 보아요🌟"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": main_msg
                    }
                },
                {
                    "simpleText": {
                        "text": commentary_msg
                    }
                },
                {
                    "simpleText": {
                        "text": footer_msg
                    }
                }
            ],
            "quickReplies": [
                 {
                    "messageText": "오늘의 QT",
                    "action": "message",
                    "label": "🔄 다시보기"
                }
            ]
        }
    }

    return JSONResponse(content=response_body)

@app.get("/")
async def root():
    return {"message": "KakaoTalk QT Bot Server is Running!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)