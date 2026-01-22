# app.py
"""
던전 경영 RPG 카카오톡 챗봇 - 메인 애플리케이션

Flask 서버를 실행하고 모든 Blueprint를 등록합니다.
"""

import os
import logging
from flask import Flask, jsonify
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 데이터베이스 연결
from database.mongodb import get_db, ping

# Blueprint import
from kakao_skills.user_skills import user_bp
from kakao_skills.monster_skills import monster_bp
from kakao_skills.dungeon_skills import dungeon_bp
from kakao_skills.battle_skills import battle_bp

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask 앱 생성
app = Flask(__name__)

# 설정
app.config['JSON_AS_ASCII'] = False  # 한글 인코딩
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True  # JSON 포맷팅


# ============================================================
# 데이터베이스 초기화 (앱 시작 시 바로 실행)
# ============================================================

try:
    logger.info("=" * 60)
    logger.info("🎮 던전 경영 RPG 챗봇 초기화 중...")
    logger.info("=" * 60)
    
    # MongoDB 연결
    db = get_db()
    logger.info(f"✅ MongoDB 연결 완료: {db.name}")
    
    # 이미지 매니저 로드
    from utils.image_manager import image_manager
    logger.info("✅ 이미지 매니저 로드 완료")
    
    logger.info("=" * 60)
    logger.info("✅ 초기화 완료!")
    logger.info("=" * 60)
    
except Exception as e:
    logger.error(f"❌ 초기화 실패: {e}", exc_info=True)


# ============================================================
# Blueprint 등록
# ============================================================

# 사용자/던전 정보 스킬
app.register_blueprint(user_bp)
logger.info("✅ User Blueprint 등록: /skill/user/*")

# 몬스터 관련 스킬
app.register_blueprint(monster_bp)
logger.info("✅ Monster Blueprint 등록: /skill/monster/*")

# 던전 관리 스킬
app.register_blueprint(dungeon_bp)
logger.info("✅ Dungeon Blueprint 등록: /skill/dungeon/*")

# 전투 관련 스킬
app.register_blueprint(battle_bp)
logger.info("✅ Battle Blueprint 등록: /skill/battle/*")


# ============================================================
# 기본 라우트
# ============================================================

@app.route('/')
def index():
    """
    메인 페이지 - 서버 상태 확인
    
    Returns:
        JSON 응답 (서버 상태)
    """
    try:
        # DB 상태 확인
        db_status = 'connected' if ping() else 'disconnected'
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        db_status = 'disconnected'
    
    return jsonify({
        'status': 'ok',
        'service': 'Dungeon RPG Chatbot',
        'version': '1.0.0',
        'database': db_status,
        'message': '던전 경영 RPG 카카오톡 챗봇이 실행 중입니다!',
        'endpoints': {
            'user': '/skill/user/*',
            'monster': '/skill/monster/*',
            'dungeon': '/skill/dungeon/*',
            'battle': '/skill/battle/*'
        }
    })


@app.route('/health')
def health_check():
    """
    헬스 체크 엔드포인트
    
    Returns:
        JSON 응답 (서버 헬스 상태)
    """
    try:
        # 데이터베이스 연결 확인
        db = get_db()
        db.command('ping')
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'message': 'All systems operational'
        })
    except Exception as e:
        logger.error(f"❌ 헬스 체크 실패: {e}")
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500


# ============================================================
# 에러 핸들러
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """
    404 에러 핸들러
    
    Args:
        error: 에러 객체
    
    Returns:
        JSON 응답 (404 에러)
    """
    return jsonify({
        'status': 'error',
        'code': 404,
        'message': '요청하신 페이지를 찾을 수 없습니다.'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """
    500 에러 핸들러
    
    Args:
        error: 에러 객체
    
    Returns:
        JSON 응답 (500 에러)
    """
    logger.error(f"❌ 내부 서버 에러: {error}", exc_info=True)
    return jsonify({
        'status': 'error',
        'code': 500,
        'message': '서버 내부 오류가 발생했습니다.'
    }), 500


# ============================================================
# 앱 실행
# ============================================================

if __name__ == '__main__':
    # 환경 변수에서 포트 가져오기 (기본값: 8080)
    port = int(os.environ.get('PORT', 8080))
    
    # 개발 모드 확인
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    logger.info("=" * 60)
    logger.info(f"🚀 Flask 서버 시작")
    logger.info(f"📍 포트: {port}")
    logger.info(f"🔧 디버그 모드: {debug_mode}")
    logger.info("=" * 60)
    
    # 서버 실행
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )