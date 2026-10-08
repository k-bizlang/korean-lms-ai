import os
import json
import logging
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google import genai
import pandas as pd

# 📌 로깅 설정 (접속 이력 및 모니터링용)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 기존에 검증된 안정적인 Gemini API 키 및 클라이언트 설정
API_KEY = "AQ.Ab8RN6JZsg1xf6Ptjx3fSDXxJB9L6g9GlR1DM1QJEc4vRCV8VA"
client = genai.Client(api_key=API_KEY)

# 💡 [성능 최적화] 가장 최근에 성공한 모델을 기억하는 전역 변수 (초기값은 None)
CACHED_SUCCESS_MODEL = None

# 📌 1. config.json 파일에서 센터 승인 및 국가/언어 설정 불러오기
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"config.json 읽기 에러: {e}")
    return {
        "DEMO_TRIAL_01": {
            "academy_name": "글로벌직무소통 하노이 교육센터",
            "country": "베트남",
            "target_language": "베트남어",
            "is_approved": True
        }
    }

# 📌 2. 장별/과별 기본 구글 드라이브 파일 ID 폴백 딕셔너리
MANAGER_DEFAULT_FILE_IDS = {
    1: "1on7JrpM4wdKwYqMMNvIs-djFSNZdhN8A", 2: "1WSc7EC8LqnAYyHSHi2dcGkFtqwwOePXs",
    3: "1i3S704xhel-CMo-iWpTeQKJsr9MK9yyj", 4: "1S2X_H6e3XsG5zNSUxr7yEm8LWZwQObmc",
    5: "1Oh_m47emmxbcopfbnf23CY53Us4NqvBv", 6: "1qBqBZETsx_cDnYHQdPawV421FVwnNS8n",
    7: "1yvC0kI4d0dAbLi_O_xF4OyCMZZIRWEsw", 8: "1pEM1ljl7K9rQySNaynfS31YdLX-7tnV9",
    9: "1_ppFdMaH3_kPxfOfgKlnjCrkAfSIGPxb", 10: "1T0k4t98YnvEwNFuepQMEuDNeDVNgZOnJ",
    11: "1uPXdQX40silkHl30NnjYeJ1E6YjwySqN", 12: "1IZsCYbNGlnJWo6YQvVv1zAL1iMWugCD2",
    13: "1JA1DQ2tgedmjxXm9uKN_1W_3PuHjZKsK", 14: "1LIQcxUIgI71ZE3Py_uZp-UklT1pAb9Av",
    15: "1gl02DQ3N9Mkc1M9VlmX04SX2ITQFYEtI", 16: "1chamQ4k5uW7xIOEWIFVNdfyFOOQ1TpCR"
}

CONSULTANT_DEFAULT_FILE_IDS = {
    1: "1-GglR8iUJ03NyFHtXRNchMohXg3imvTw", 2: "1YIc0ZIS7NEhjf1fijFaaa_4WD1XyKAIp",
    3: "1lJPV3i_beLHjiHVEzw8K_sXaYGc6B1-6", 4: "1CI1wJBhP-v40iEcMmtJttEwefK7Hyo13",
    5: "17zQ6Btk8zTbTpXy2IjM18WYXAWwFLJnT", 6: "1UHI6Vvvv_ptWWaPL9hWJ4LLOQB9u78Sd",
    7: "1nZRILkspeyprgfQDvUTrbcSTxA6EsGuI", 8: "13trnGbLIDYXRwlItlH8D1aQQvJIrH877",
    9: "1VuIYkuQvKEkbcY8GkSqtGUz7bU_oqsAE", 10: "1Ospd1bCMCfqkHXlDWb2YRoPZNuKnc6gQ",
    11: "1rsNUKaAVQVPDeIKmUAo8gUOJ6qKxqBJe", 12: "1SmFwuPFquBxX_5u8K-7eQFXWPGfo8CBO",
    13: "1xFrouhEaDLyHY-ABcn4U0L0TWxEh94OS", 14: "1ev3ZqKQek71Q2hCrjwJysylTuNZftsRz"
}

def load_curriculum_csv():
    csv_path = os.path.join(os.path.dirname(__file__), "curriculum.csv")
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig', quotechar='"', on_bad_lines='skip')
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        logging.error(f"CSV 로딩 에러: {e}")
        return pd.DataFrame()

# 📌 3. 센터 ID 승인 검증 및 강의 데이터 연동 API
@app.get("/api/lesson-data")
async def get_lesson_data(
    academy_code: str = Query(...), 
    course_type: str = "manager", 
    chapter: int = 1, 
    page: int = 1
):
    configs = load_config()
    clean_code = str(academy_code).strip()
    
    if clean_code not in configs or not configs[clean_code].get("is_approved", False):
        raise HTTPException(status_code=403, detail="승인되지 않았거나 존재하지 않는 센터 ID입니다. 올바른 ID를 입력해 주세요.")
    
    academy_info = configs[clean_code]
    logging.info(f"📥 [접속 승인 완료] 센터명: {academy_info['academy_name']} ({clean_code})")

    raw_type = str(course_type).lower().strip()
    c_type = "consultant" if "consultant" in raw_type or "컨설턴트" in raw_type else "manager"
    
    max_chapter = 16 if c_type == "manager" else 14
    final_chapter = max(1, min(int(chapter), max_chapter))
    final_page = max(1, int(page))
 
    chapter_title = f"[{c_type.upper()}] 제{final_chapter}장 직무 교육"
    page_content_text = "현재 페이지의 강의 대본을 준비 중입니다."
    
    if c_type == "manager":
        drive_file_id = MANAGER_DEFAULT_FILE_IDS.get(final_chapter, "1on7JrpM4wdKwYqMMNvIs-djFSNZdhN8A")
    else:
        drive_file_id = CONSULTANT_DEFAULT_FILE_IDS.get(final_chapter, "1-GglR8iUJ03NyFHtXRNchMohXg3imvTw")

    df_curriculum = load_curriculum_csv()
    if not df_curriculum.empty:
        try:
            df_curriculum['chapter_num'] = pd.to_numeric(df_curriculum['chapter_num'], errors='coerce')
            df_curriculum['page_num'] = pd.to_numeric(df_curriculum['page_num'], errors='coerce')
            
            matched = df_curriculum[
                (df_curriculum['course_type'].astype(str).str.strip().str.lower() == c_type) & 
                (df_curriculum['chapter_num'] == final_chapter) & 
                (df_curriculum['page_num'] == final_page)
            ]
            
            if not matched.empty:
                row = matched.iloc[0]
                if pd.notna(row.get('chapter_title')):
                    chapter_title = str(row['chapter_title']).strip()
                if pd.notna(row.get('page_content_text')):
                    page_content_text = str(row['page_content_text']).strip()
                if pd.notna(row.get('drive_file_id')) and str(row.get('drive_file_id')).strip() != "":
                    drive_file_id = str(row.get('drive_file_id')).strip()
        except Exception as e:
            logging.error(f"CSV 검색 에러: {e}")

    max_page_num = 11
    if not df_curriculum.empty:
        try:
            matched_chapter_pages = df_curriculum[
                (df_curriculum['course_type'].astype(str).str.strip().str.lower() == c_type) & 
                (df_curriculum['chapter_num'] == final_chapter)
            ]
            if not matched_chapter_pages.empty:
                max_page_num = int(matched_chapter_pages['page_num'].max())
        except Exception as e:
            logging.error(f"최대 페이지 계산 에러: {e}")

    return {
        "academy_code": clean_code,
        "academy_name": academy_info["academy_name"],
        "country": academy_info["country"],
        "target_language": academy_info["target_language"],
        "course_type": c_type,
        "chapter": final_chapter,
        "page": final_page,
        "max_chapter": max_chapter,
        "max_page": max_page_num,
        "chapter_title": chapter_title,
        "page_content_text": page_content_text,
        "drive_file_id": drive_file_id
    }

# 📌 4. Gemini AI 튜터 API (스마트 캐싱 및 응답 속도 최적화 적용)
class QuestionRequest(BaseModel):
    academy_code: str
    course_type: str
    chapter_title: str
    current_page: int
    page_content_text: str
    student_message: str

@app.post("/api/ai-tutor")
async def ai_tutor_gateway(data: QuestionRequest):
    global CACHED_SUCCESS_MODEL  # 전역 성공 모델 변수 참조

    configs = load_config()
    clean_code = str(data.academy_code).strip()
    if clean_code not in configs or not configs[clean_code].get("is_approved", False):
        raise HTTPException(status_code=403, detail="인증되지 않은 접근입니다.")
        
    academy_info = configs[clean_code]
    country = academy_info["country"]
    target_lang = academy_info["target_language"]
    
    msg = data.student_message.strip()
    if not msg:
        return {"reply": "질문 내용을 입력해 주세요."}

    # 📌 음성(TTS) 가독성을 위한 기호 금지 + 요약/상세 유연 대응 프롬프트
    system_prompt = (
        f"당신은 직무 한국어 교육 기관의 수석 교사 '지니 선생님'입니다.\n"
        f"교육생 소속 국가: {country} (현지어: {target_lang})\n"
        f"현재 수업 위치: {data.chapter_title} (페이지 {data.current_page})\n"
        f"현재 페이지 참고 대본: \"{data.page_content_text}\"\n\n"
        f"지침:\n"
        f"1. 음성(TTS) 출력을 방해하는 #, *, -, _ 등의 마크다운 기호나 특수문자는 절대 사용하지 마세요.\n"
        f"2. 기본 질문에는 핵심 내용 위주로 짧고 간결하게 답변하세요.\n"
        f"3. 단, 교육생이 '자세히 알려줘', '더 설명해줘', '예시를 들어줘' 등 구체적인 추가 설명을 요구할 경우에는 현장 업무 예시를 포함하여 아주 자세하고 친절하게 확장해서 설명해 주세요.\n"
        f"4. 말투는 항상 온화하고 차분하며 거부감이 전혀 없는 다정한 어조를 유지하세요.\n"
        f"5. 한국어 설명과 함께 {country}의 {target_lang}(현지어) 번역을 함께 병기해 주세요."
    )
    
    # 💡 기본 전체 모델 후보군 리스트
    default_candidates = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash"
    ]

    # 💡 [속도 최적화] 만약 이전에 성공했던 모델이 있다면, 그 모델을 리스트 맨 앞으로 끌어올려 즉시 시도하게 함!
    if CACHED_SUCCESS_MODEL and CACHED_SUCCESS_MODEL in default_candidates:
        model_candidates = [CACHED_SUCCESS_MODEL] + [m for m in default_candidates if m != CACHED_SUCCESS_MODEL]
    else:
        model_candidates = default_candidates

    response_text = None
    last_error = None

    # 다중 통신망 순환 및 자동 재시도 로직
    for model_name in model_candidates:
        try:
            logging.info(f"🔄 AI 통신 시도 중 -> 모델: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=f"{system_prompt}\n\n교육생 질문: {msg}"
            )
            
            if response and response.text:
                response_text = response.text
                
                # 🚀 성공한 모델을 캐시에 저장! 다음 질문부터는 이 모델로 다이렉트 접속하여 응답 속도가 대폭 단축됨
                CACHED_SUCCESS_MODEL = model_name
                logging.info(f"✅ AI 통신 성공 및 모델 캐싱 완료! (사용 모델: {model_name})")
                
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    total_t = response.usage_metadata.total_token_count
                    logging.info(f"📊 [AI 토큰 소모량] 센터:{clean_code} | 총 토큰: {total_t}")
                
                break  
                
        except Exception as model_err:
            logging.warning(f"⚠️ 모델 '{model_name}' 통신 실패, 3초 후 다음 경로로 전환합니다. 사유: {model_err}")
            time.sleep(3)  
            last_error = model_err

    if not response_text:
        logging.error(f"🚨 제미나이 최종 통신 장애 발생: {last_error}")
        return {"reply": "죄송합니다. 일시적인 통신 장애로 답변을 생성하지 못했습니다. 잠시 후 다시 질문해 주세요."}

    return {"reply": response_text}

# 📌 5. 루트 주소로 접속했을 때 index.html을 브라우저에 띄워주는 라우터
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    html_path = "index.html"
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>index.html 파일을 찾을 수 없습니다. working directory를 확인해주세요.</h1>"