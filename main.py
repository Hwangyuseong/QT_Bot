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

# 매일성경 순 (청소년/청년용) URL (?qt_ty=QT6)
QT_URL = "https://sum.su.or.kr:8888/bible/today?qt_ty=QT6"

async def fetch_qt_data():
    """
    매일성경 순(QT6) 내용을 크롤링합니다.
    (성경 본문 구절 제외 / 해설 전문 포함)
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

        # 2. 해설 (성경 이해 등 포함된 전체 해설)
        # 성경 본문 구절(#body_list) 대신 해설(#commentary_view)을 가져옵니다.
        commentary_element = soup.select_one("#commentary_view")
        
        if commentary_element:
            # 보기 좋게 줄바꿈 처리
            commentary_text = commentary_element.get_text(separator="\n", strip=True)
        else:
            commentary_text = "해설 내용을 불러올 수 없습니다."

        return {
            "title": title_text,
            "bible_ref": bible_ref,
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

    # --- 카카오톡 응답 생성 (내용 분할 알고리즘) ---
    # 카카오톡 말풍선 1개 한계: 1000자
    # 전략: 
    # 1. 첫 번째 말풍선: 제목 + 본문 범위 + 해설 앞부분 (약 900자)
    # 2. 두 번째 말풍선: 해설 뒷부분 (나머지)
    # 3. 세 번째 말풍선: 링크 + 인사말

    outputs = []
    
    # -- 헤더 생성 --
    header = f"✝오늘의 QT(순)✝\n\n[{qt_data['title']}]\n본문: {qt_data['bible_ref']}\n\n"
    
    # 해설 전체 텍스트
    full_commentary = qt_data['commentary']
    
    # 첫 번째 말풍선에 들어갈 해설 길이 계산 (안전하게 950자 - 헤더길이)
    limit_len = 950 - len(header)
    
    part_1 = full_commentary[:limit_len]
    part_2 = full_commentary[limit_len:] # 남은 뒷부분
    
    # 1. 첫 번째 말풍선 추가
    outputs.append({
        "simpleText": {
            "text": header + part_1
        }
    })
    
    # 2. 두 번째 말풍선 추가 (내용이 남았을 경우에만)
    if part_2:
        # 두 번째 말풍선도 1000자를 넘으면 또 잘라야 함 (카톡 최대 3개 말풍선 제한 때문)
        # 링크 말풍선(3번)을 위해 여기서는 최대 1000자까지만 보여주고 나머지는 생략
        if len(part_2) > 1000:
             part_2 = part_2[:950] + "\n...(내용이 더 있습니다. 아래 링크를 확인해주세요)"
             
        outputs.append({
            "simpleText": {
                "text": part_2
            }
        })

    # 3. 세 번째 말풍선 (링크 및 인사말)
    footer_msg = f"🔗 해설 전문 보기: {qt_data['url']}\n\n🌟아침에 말씀으로 시작하며 하나님의 은혜 충만으로 하루를 시작해 보아요🌟"
    outputs.append({
        "simpleText": {
            "text": footer_msg
        }
    })

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": outputs,
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
    return {"message": "KakaoTalk QT Bot Server (Fix Split Ver) is Running!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)