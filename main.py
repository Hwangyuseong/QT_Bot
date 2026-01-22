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
    (HTML 구조: .body_cont > .b_text, .g_text, .text 파싱)
    """
    try:
        # User-Agent 헤더 추가
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(QT_URL)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 날짜 및 제목 추출
        title_element = soup.select_one("#bible_text") 
        sub_title_element = soup.select_one("#bibleinfo_box") 
        
        title_text = title_element.get_text(strip=True) if title_element else "제목 없음"
        bible_ref = sub_title_element.get_text(strip=True) if sub_title_element else "본문 정보 없음"

        # 2. 해설 파싱 (수정된 로직)
        # 제공해주신 HTML 구조: .body_cont > div(.b_text, .g_text, .text)
        body_cont = soup.select_one(".body_cont")
        
        commentary_text = ""
        if body_cont:
            # .body_cont 바로 아래 자식 div들을 순서대로 순회하며 텍스트 조합
            for child in body_cont.find_all("div", recursive=False):
                text = child.get_text(separator="\n", strip=True)
                if not text:
                    continue
                
                classes = child.get("class", [])
                
                if "b_text" in classes:
                    # 묵상 서론 (굵은 글씨 등 강조 필요 시 처리 가능하나 여기선 텍스트만)
                    commentary_text += text + "\n\n"
                    
                elif "g_text" in classes:
                    # 소제목 (성경 이해, 나의 적용, 기도하기 등) -> 이모지 추가
                    # 이미 텍스트에 "성경 이해"가 포함되어 있으므로 앞에 이모지만 붙임
                    commentary_text += f"📖 {text}\n"
                    
                elif "text" in classes:
                    # 본문 내용
                    commentary_text += text + "\n\n"
        else:
            commentary_text = "해설 내용을 불러올 수 없습니다."

        # 만약 크롤링 결과가 비어있다면 에러 메시지
        if not commentary_text.strip():
             commentary_text = "해설 내용을 찾을 수 없습니다 (HTML 구조 변경 가능성)."

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
    outputs = []
    
    # -- 헤더 생성 --
    header = f"✝오늘의 QT(순)✝\n\n[{qt_data['title']}]\n본문: {qt_data['bible_ref']}\n\n"
    
    full_commentary = qt_data['commentary']
    
    # 첫 번째 말풍선 길이 제한 (헤더 포함 1000자 이내)
    limit_len = 950 - len(header)
    
    part_1 = full_commentary[:limit_len]
    part_2 = full_commentary[limit_len:] 
    
    # 1. 첫 번째 말풍선
    outputs.append({
        "simpleText": {
            "text": header + part_1
        }
    })
    
    # 2. 두 번째 말풍선 (남은 내용이 있을 경우)
    if part_2:
        if len(part_2) > 1000:
             part_2 = part_2[:950] + "\n...(내용 더 있음)"
             
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
    return {"message": "KakaoTalk QT Bot Server (Fixed Parser Ver) is Running!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)