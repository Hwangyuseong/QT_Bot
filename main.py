import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 수정됨: 매일성경 순 (청소년/청년용) URL로 변경 (?qt_ty=QT6 추가)
QT_URL = "https://sum.su.or.kr:8888/bible/today?qt_ty=QT6"

async def fetch_qt_data():
    """
    매일성경 순(QT6) 내용을 크롤링합니다.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(QT_URL)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 날짜 및 제목 추출
        title_element = soup.select_one("#bible_text") 
        sub_title_element = soup.select_one("#bibleinfo_box") 
        
        title_text = title_element.get_text(strip=True) if title_element else "제목 없음"
        bible_ref = sub_title_element.get_text(strip=True) if sub_title_element else "본문 정보 없음"

        # 2. 본문 텍스트
        body_text_element = soup.select_one("#body_list")
        bible_text = body_text_element.get_text(separator="\n", strip=True) if body_text_element else "본문을 불러올 수 없습니다."
        
        # 3. 찬송 (없으면 '-')
        song_text = "-" 

        return {
            "title": title_text,
            "bible_ref": bible_ref,
            "bible_text": bible_text,
            "song": song_text,
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
        return JSONResponse(content={
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": "죄송합니다. 큐티 정보를 가져오는데 실패했습니다."
                        }
                    }
                ]
            }
        })

    # --- 카카오톡 응답 생성 ---
    
    # 1. 첫 번째 말풍선: 제목, 본문 (기존 유지)
    main_msg = f"✝오늘의 QT(매일성경(순))✝\n\n[{qt_data['title']}]\n본문: {qt_data['bible_ref']}\n\n{qt_data['bible_text'][:800]}"
    if len(qt_data['bible_text']) > 800:
        main_msg += "..."

    # 2. 두 번째 말풍선: 해설 (요청사항: '오늘의 묵상' 타이틀 제거)
    commentary_msg = f"{qt_data['commentary'][:900]}"
    if len(qt_data['commentary']) > 900:
        commentary_msg += "...\n(더보기는 버튼 클릭)"

    # 3. 세 번째 말풍선: BasicCard (요청사항: 버튼으로 변경)
    # 이미지가 없는 베이직 카드 + 버튼 조합
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
                    "basicCard": {
                        "title": "오늘 하루도 승리하세요! 🙏",
                        "description": "아침에 말씀으로 시작하며 하나님의 은혜 충만으로 하루를 시작해 보아요",
                        "buttons": [
                            {
                                "action": "webLink",
                                "label": "해설 전문 보기",
                                "webLinkUrl": qt_data['url']
                            }
                        ]
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
    return {"message": "KakaoTalk QT Bot Server (Soon Ver) is Running!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)