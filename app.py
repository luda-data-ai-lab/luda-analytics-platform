import re
from urllib.parse import urljoin, urlparse

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, send_file,
    send_from_directory, session
)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup, escape
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename
from sqlalchemy.exc import SQLAlchemyError
from config import Config
import io
import logging
import pandas as pd
import json
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objs as go
from models import db, User, Dataset, DataRecord, DataView, OCRSession
from src.advanced_analytics import (
    AGG_FUNCS, FREQ_RULES, categorical_columns, contribution_analysis, correlation_analysis,
    datetime_columns, numeric_columns, outlier_analysis, timeseries_analysis
)
from src.segment_analytics import (
    AB_METRICS, ab_test_analysis, cohort_analysis, pareto_analysis, rfm_analysis
)
from src.analysis_utils import (
    add_ratio_column, correlation, gain_pct, group_agg, ratio_pct, top_share
)
from src.chart_utils import (
    BASE_LAYOUT, QUALITATIVE_COLORS, add_month_column, distribution_by_group,
    go_bar_categorical, go_scatter, group_sum, grouped_bar, histogram_by_group,
    horizontal_bar, line_trend, pie_chart, resolve_column, resolve_columns, simple_bar,
    value_counts_frame
)
from src.dataset_utils import (
    create_dataset_with_records, dataframe_rows, fix_dataset_meta, load_dataset_dataframe,
    read_dataframe, remove_file, save_upload, upload_folder
)
from src.i18n import flash_msg, get_message, msg

# 기존 이름 유지 (테스트/기존 호출부 호환)
_go_scatter = go_scatter
_go_bar_categorical = go_bar_categorical
_fix_dataset_meta = fix_dataset_meta
_remove_file = remove_file


logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# CSRF 보호 (모든 상태 변경 요청)
csrf = CSRFProtect(app)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD_LENGTH = 8

# 인사이트 문구에서 허용하는 태그만 복원하는 화이트리스트 (업로드 데이터 기반 XSS 방지)
_ALLOWED_INSIGHT_TAGS = ('strong', 'em', 'br')


@app.template_filter('insight_html')
def insight_html(value):
    """인사이트 문구를 이스케이프하고 서식용 태그만 허용"""
    if not value:
        return ''
    safe = str(escape(value))
    for tag in _ALLOWED_INSIGHT_TAGS:
        safe = safe.replace(f'&lt;{tag}&gt;', f'<{tag}>').replace(f'&lt;/{tag}&gt;', f'</{tag}>')
    return Markup(safe)


def is_safe_redirect_url(target):
    """같은 호스트로의 상대 경로만 리다이렉트 허용 (open redirect 방지)"""
    if not target:
        return False
    parsed = urlparse(urljoin(request.host_url, target))
    return parsed.scheme in ('http', 'https') and parsed.netloc == urlparse(request.host_url).netloc

# 데이터베이스 초기화
db.init_app(app)

# 로그인 매니저 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        logger.warning("세션의 사용자 ID가 유효하지 않습니다: %r", user_id)
        return None


# 분석 단계 이름 (로그용 영문, 사용자 표시용 한/영)
STAGE_CHARTS = ('차트', 'Charts')
STAGE_METRICS = ('지표', 'Metrics')
STAGE_INSIGHTS = ('인사이트', 'Insights')


def _record_failure(failures, stage, exc):
    """분석 단계의 실패를 로그에 남기고 호출자에게 단계 이름을 전달한다.

    요청 컨텍스트 밖에서도 호출될 수 있으므로 현지화는 flash 시점으로 미룬다.
    """
    logger.exception("%s 생성 실패: %s", stage[1], exc)
    if failures is not None:
        failures.append(stage)


def _flash_analysis_failures(failures):
    """실패한 단계 이름만 알린다 (예외 상세는 서버 로그에만 남긴다)."""
    if not failures:
        return
    stages = ' / '.join(get_message(ko, en) for ko, en in failures)
    flash(get_message(
        f'일부 분석 결과를 생성하지 못했습니다. ({stages})',
        f'Some analysis results could not be generated. ({stages})'
    ), 'warning')


def _commit_or_flash(error_ko, error_en):
    """커밋을 시도하고, 실패 시 롤백·로그·flash 후 False 를 반환한다."""
    try:
        db.session.commit()
        return True
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(error_en)
        flash(get_message(error_ko, error_en), 'danger')
        return False


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    logger.warning("업로드 용량 초과: %s", error)
    flash(get_message(
        f'파일 크기가 너무 큽니다. (최대 {limit_mb}MB)',
        f'File is too large. (max {limit_mb}MB)'
    ), 'danger')
    referrer = request.referrer
    if referrer and is_safe_redirect_url(referrer):
        return redirect(referrer)
    return redirect(url_for('index'))

# 언어 설정
@app.before_request
def before_request():
    if 'language' not in session:
        session['language'] = app.config['DEFAULT_LANGUAGE']

@app.route('/set_language/<language>')
def set_language(language):
    if language in app.config['LANGUAGES']:
        session['language'] = language
    referrer = request.referrer
    if referrer and is_safe_redirect_url(referrer):
        return redirect(referrer)
    return redirect(url_for('index'))

@app.context_processor
def inject_language():
    return dict(current_language=session.get('language', 'ko'))

# 파일 확장자 확인
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# 홈 페이지
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# 회원가입
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        name = (request.form.get('name') or '').strip()
        company = (request.form.get('company') or '').strip()  # 회사명 추가 (선택사항)

        if not email or not password or not name:
            flash(get_message('이메일, 이름, 비밀번호를 모두 입력해주세요.', 'Email, name and password are required.'), 'danger')
            return redirect(url_for('register'))

        if not EMAIL_RE.match(email) or len(email) > 120:
            flash(get_message('올바른 이메일 주소를 입력해주세요.', 'Please enter a valid email address.'), 'danger')
            return redirect(url_for('register'))

        if len(password) < MIN_PASSWORD_LENGTH:
            flash(
                get_message(
                    f'비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.',
                    f'Password must be at least {MIN_PASSWORD_LENGTH} characters long.',
                ),
                'danger',
            )
            return redirect(url_for('register'))

        if len(name) > 100 or len(company) > 100:
            flash(get_message('이름 또는 회사명이 너무 깁니다.', 'Name or company is too long.'), 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash(get_message('이미 등록된 이메일입니다.', 'Email already registered.'), 'danger')
            return redirect(url_for('register'))
        
        user = User(email=email, name=name, company=company)
        user.set_password(password)

        db.session.add(user)
        if not _commit_or_flash('회원가입 처리 중 오류가 발생했습니다.', 'Registration failed.'):
            return redirect(url_for('register'))

        flash(get_message('회원가입이 완료되었습니다!', 'Registration successful!'), 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# 로그인
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        remember = bool(request.form.get('remember', False))

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(get_message('로그인 되었습니다.', 'Successfully logged in.'), 'success')
            next_page = request.args.get('next')
            if next_page and is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash(get_message('이메일 또는 비밀번호가 올바르지 않습니다.', 'Invalid email or password.'), 'danger')
    
    return render_template('login.html')

# 로그아웃
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash(get_message('로그아웃 되었습니다.', 'Successfully logged out.'), 'success')
    return redirect(url_for('index'))

# 대시보드
@app.route('/dashboard')
@login_required
def dashboard():
    view = request.args.get('view', 'my')  # 'my' or 'company'

    if view == 'company' and current_user.company:
        company_user_ids = [
            u.id for u in User.query.filter_by(company=current_user.company).all()
        ]
        datasets = Dataset.query.filter(
            Dataset.user_id.in_(company_user_ids)
        ).order_by(Dataset.uploaded_at.desc()).all()
    else:
        view = 'my'
        datasets = Dataset.query.filter_by(
            user_id=current_user.id
        ).order_by(Dataset.uploaded_at.desc()).all()

    return render_template('dashboard.html', datasets=datasets, view=view)

# 데이터 업로드
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash_msg('no_file_selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if file.filename == '':
            flash_msg('no_file_selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            try:
                filepath, _ = save_upload(file, current_user.id)
            except OSError:
                logger.exception("업로드 파일 저장 실패: %s", file.filename)
                flash_msg('save_failed', 'danger')
                return redirect(url_for('upload'))

            try:
                df = read_dataframe(filepath)
                dataset = create_dataset_with_records(
                    df, name=name, description=description,
                    filename=file.filename, file_path=filepath,
                    user_id=current_user.id
                )
                db.session.commit()
                flash_msg('data_uploaded', 'success')
                return redirect(url_for('view_dataset', dataset_id=dataset.id))
            
            except Exception:
                db.session.rollback()
                logger.exception("데이터 업로드 실패: %s", filepath)
                flash_msg('process_failed', 'danger')
                remove_file(filepath)
                return redirect(url_for('upload'))
        else:
            flash_msg('invalid_file_format', 'danger')
    
    return render_template('upload.html')

def _deny_if_not_owner(record, endpoint):
    """소유자가 아니면 flash 후 리다이렉트 생성 (소유자라면 None)."""
    if record.user_id != current_user.id:
        flash_msg('access_denied', 'danger')
        return redirect(url_for(endpoint))
    return None


# 데이터셋 보기
@app.route('/dataset/<int:dataset_id>')
@login_required
def view_dataset(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)

    denied = _deny_if_not_owner(dataset, 'dashboard')
    if denied:
        return denied

    fix_dataset_meta(dataset)
    records = DataRecord.query.filter_by(dataset_id=dataset_id).limit(100).all()
    data = [record.data for record in records]

    return render_template('view_dataset.html', dataset=dataset, data=data, columns=dataset.columns or [])

# 데이터 시각화
@app.route('/visualize/<int:dataset_id>')
@login_required
def visualize(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)

    denied = _deny_if_not_owner(dataset, 'dashboard')
    if denied:
        return denied

    fix_dataset_meta(dataset)
    columns = dataset.columns if dataset.columns is not None else []
    return render_template('visualize.html', dataset=dataset, columns=columns)

# 차트 생성 API
@app.route('/api/generate_chart', methods=['POST'])
@login_required
def generate_chart():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': get_message('요청 본문이 유효한 JSON이 아닙니다.', 'Request body is not valid JSON.')}), 400

        dataset_id = data.get('dataset_id')
        chart_type = data.get('chart_type')
        x_column = data.get('x_column')
        y_column = data.get('y_column')

        if not dataset_id or not chart_type or not x_column:
            return jsonify({'error': get_message('dataset_id, chart_type, x_column은 필수입니다.',
                                                 'dataset_id, chart_type and x_column are required.')}), 400
        
        print(f"\n=== 차트 생성 요청 / Chart Generation Request ===")
        print(f"Dataset ID: {dataset_id}")
        print(f"Chart Type: {chart_type}")
        print(f"X Column: {x_column}")
        print(f"Y Column: {y_column}")
        
        dataset = Dataset.query.get_or_404(dataset_id)
        
        if dataset.user_id != current_user.id:
            return jsonify({'error': msg('access_denied')}), 403
        
        # 데이터 레코드 가져오기
        df = load_dataset_dataframe(dataset_id)
        if df.empty:
            return jsonify({'error': msg('no_data')}), 400
        
        print(f"총 레코드 수 / Total records: {len(df)}")
        print(f"DataFrame shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        
        # 컬럼 존재 확인
        if x_column not in df.columns:
            return jsonify({'error': get_message(f'컬럼을 찾을 수 없습니다: {x_column}', f'Column not found: {x_column}')}), 400
        if y_column and y_column not in df.columns:
            return jsonify({'error': get_message(f'컬럼을 찾을 수 없습니다: {y_column}', f'Column not found: {y_column}')}), 400
        
        # 데이터 샘플 출력
        print(f"\n원본 데이터 샘플 (처음 3행):")
        print(df.head(3))
        
        # 데이터 타입 확인
        print(f"\n원본 데이터 타입 / Original data types:")
        print(f"X ({x_column}): {df[x_column].dtype}")
        if y_column:
            print(f"Y ({y_column}): {df[y_column].dtype}")
            print(f"Y 값 샘플: {df[y_column].head(3).tolist()}")
        
        # 데이터 타입 변환 (날짜와 숫자 모두 지원)
        is_y_date = False  # Y축이 날짜인지 여부
        is_x_date = False  # X축이 날짜인지 여부
        
        try:
            if chart_type in ['line', 'bar', 'scatter', 'histogram']:
                # Y축 데이터 처리 (날짜 우선, 그 다음 숫자)
                if y_column and y_column in df.columns:
                    # 원본 데이터 타입 확인
                    original_dtype = df[y_column].dtype
                    print(f"Y축 원본 타입: {original_dtype}")
                    
                    # 1. 날짜로 변환 시도 (숫자 타입이 아닌 경우만)
                    if original_dtype == 'object':  # 문자열 타입일 때만 날짜 변환 시도
                        try:
                            # 샘플 데이터로 날짜 형식 검증
                            sample_val = str(df[y_column].iloc[0])
                            # 날짜 형식 패턴 체크 (YYYY-MM-DD, YYYY/MM/DD 등)
                            if any(sep in sample_val for sep in ['-', '/', '.']):
                                temp_y = pd.to_datetime(df[y_column], errors='coerce')
                                # 80% 이상 성공적으로 변환되면 날짜로 인식
                                if temp_y.notna().sum() / len(temp_y) > 0.8:
                                    df[y_column] = temp_y
                                    is_y_date = True
                                    print(f"✅ Y축을 날짜로 변환함")
                                    print(f"Y 컬럼 변환 후 dtype: {df[y_column].dtype}")
                                    print(f"Y 컬럼 변환 후 샘플: {df[y_column].head(3).tolist()}")
                                else:
                                    raise ValueError("Not enough valid dates")
                            else:
                                raise ValueError("No date separator found")
                        except (ValueError, TypeError, IndexError, KeyError) as date_error:
                            # 날짜 변환 실패 -> 숫자 변환 시도
                            logger.debug("Y축 날짜 변환 실패(숫자로 재시도): %s", date_error)
                            df[y_column] = df[y_column].astype(str).str.replace(',', '').str.replace(' ', '')
                            df[y_column] = pd.to_numeric(df[y_column], errors='coerce')
                            print(f"Y 컬럼을 숫자로 변환함")
                            print(f"Y 컬럼 변환 후 dtype: {df[y_column].dtype}")
                            print(f"Y 컬럼 변환 후 샘플: {df[y_column].head(3).tolist()}")
                    else:
                        # 이미 숫자 타입이면 그대로 사용 또는 숫자 변환
                        df[y_column] = df[y_column].astype(str).str.replace(',', '').str.replace(' ', '')
                        df[y_column] = pd.to_numeric(df[y_column], errors='coerce')
                        print(f"Y 컬럼을 숫자로 변환함 (원본이 숫자 타입)")
                        print(f"Y 컬럼 변환 후 dtype: {df[y_column].dtype}")
                        print(f"Y 컬럼 변환 후 샘플: {df[y_column].head(3).tolist()}")
                
                # X축 처리
                if chart_type == 'histogram':
                    # 히스토그램은 X축도 숫자여야 함
                    df[x_column] = df[x_column].astype(str).str.replace(',', '').str.replace(' ', '')
                    df[x_column] = pd.to_numeric(df[x_column], errors='coerce')
                else:
                    # 라인/바/산점도의 경우 X축을 날짜로 변환 시도
                    original_x_dtype = df[x_column].dtype
                    if original_x_dtype == 'object':  # 문자열 타입일 때만
                        try:
                            sample_x_val = str(df[x_column].iloc[0])
                            # 날짜 형식 패턴 체크
                            if any(sep in sample_x_val for sep in ['-', '/', '.']):
                                temp_x = pd.to_datetime(df[x_column], errors='coerce')
                                # 80% 이상 성공적으로 변환되면 날짜로 인식
                                if temp_x.notna().sum() / len(temp_x) > 0.8:
                                    df[x_column] = temp_x
                                    is_x_date = True
                                    print(f"✅ X축을 날짜로 변환함")
                        except (ValueError, TypeError, IndexError, KeyError) as date_error:
                            logger.debug("X축 날짜 변환 실패(원본 값 사용): %s", date_error)
            
            elif chart_type == 'pie':
                # 파이 차트는 values를 숫자로 변환, names는 문자열로 유지
                if y_column:
                    # Y축(values)을 숫자로 변환
                    df[y_column] = df[y_column].astype(str).str.replace(',', '').str.replace(' ', '')
                    df[y_column] = pd.to_numeric(df[y_column], errors='coerce')
                    print(f"파이 차트 Y 변환 후: {df[y_column].dtype}")
                # X축(names)은 문자열로 유지 (카테고리)
                df[x_column] = df[x_column].astype(str)
                print(f"파이 차트 X를 문자열로 유지: {df[x_column].dtype}")
                print(f"X 값 샘플: {df[x_column].head(3).tolist()}")
        
        except Exception:
            logger.exception("데이터 변환 실패: dataset_id=%s, x=%s, y=%s", dataset_id, x_column, y_column)
            return jsonify({'error': get_message(
                '선택한 컬럼을 차트용 데이터로 변환하지 못했습니다.',
                'Could not convert the selected columns into chart data.'
            )}), 400
        
        # NaN 값 제거
        before_dropna = len(df)
        if y_column:
            df = df.dropna(subset=[y_column])
        if chart_type == 'histogram':
            df = df.dropna(subset=[x_column])
        after_dropna = len(df)
        
        if before_dropna != after_dropna:
            print(f"NaN 제거: {before_dropna} → {after_dropna} 행")
        
        # 데이터가 충분한지 확인
        if len(df) == 0:
            return jsonify({'error': get_message('유효한 데이터가 없습니다. 숫자 데이터를 포함한 컬럼을 선택하세요.', 'No valid data. Please select columns with numeric data.')}), 400
        
        print(f"최종 데이터 행 수 / Final data rows: {len(df)}")
        
        # 데이터 정렬 (X축 기준)
        if chart_type in ['line', 'bar']:
            try:
                # 날짜나 숫자인 경우 정렬
                if df[x_column].dtype in ['datetime64[ns]', 'int64', 'float64']:
                    df = df.sort_values(by=x_column)
                    print(f"X축 기준으로 정렬됨")
                    # 인덱스 리셋 (중요!)
                    df = df.reset_index(drop=True)
            except (TypeError, ValueError, KeyError):
                # 정렬은 부가 기능이므로 차트는 계속 생성하되, 원인은 로그로 남긴다.
                logger.warning("X축 정렬 실패: dataset_id=%s, column=%s", dataset_id, x_column, exc_info=True)
        
        print(f"\n최종 데이터 샘플 (처음 5행):")
        print(df[[x_column, y_column] if y_column else [x_column]].head(5))
        
        # Plotly에 전달할 실제 데이터 확인
        print(f"\nPlotly에 전달할 데이터:")
        print(f"X 데이터 (처음 5개): {df[x_column].head(5).tolist()}")
        if y_column:
            print(f"Y 데이터 (처음 5개): {df[y_column].head(5).tolist()}")
            print(f"Y 데이터 타입: {df[y_column].dtype}")
            print(f"Y 데이터 최소값: {df[y_column].min()}")
            print(f"Y 데이터 최대값: {df[y_column].max()}")
        
        # 차트 생성
        try:
            # 데이터 복사본 생성 (원본 보존)
            plot_df = df.copy()
            
            if chart_type == 'line':
                print(f"\n라인 차트 생성 중...")
                fig = px.line(plot_df, x=x_column, y=y_column, 
                            title=get_message(f'{y_column} vs {x_column}', f'{y_column} vs {x_column}'),
                            markers=True)
                # Y축 설정 - 날짜 타입 고려
                if is_y_date:
                    fig.update_yaxes(title_text=y_column, type='date', autorange=True)
                else:
                    fig.update_yaxes(title_text=y_column, autorange=True)
                # X축 설정
                if is_x_date:
                    fig.update_xaxes(title_text=x_column, type='date')
                else:
                    fig.update_xaxes(title_text=x_column)
            
            elif chart_type == 'bar':
                print(f"\n바 차트 생성 중...")
                # 같은 카테고리가 여러 행에 걸쳐 있으면 합계로 집계 (누적 막대 대신 하나의 막대)
                if (not is_x_date and not is_y_date
                        and pd.api.types.is_numeric_dtype(plot_df[y_column])
                        and plot_df[x_column].duplicated().any()):
                    plot_df = (plot_df.groupby(x_column, as_index=False)[y_column]
                               .sum()
                               .sort_values(y_column, ascending=False))
                fig = px.bar(plot_df, x=x_column, y=y_column, 
                           title=get_message(f'{x_column}별 {y_column}', f'{y_column} by {x_column}'))
                # Y축 설정 - 날짜 타입 고려
                if is_y_date:
                    fig.update_yaxes(title_text=y_column, type='date', autorange=True)
                else:
                    fig.update_yaxes(title_text=y_column, autorange=True)
                # X축 설정
                if is_x_date:
                    fig.update_xaxes(title_text=x_column, type='date')
                else:
                    fig.update_xaxes(title_text=x_column)
            
            elif chart_type == 'scatter':
                print(f"\n산점도 생성 중...")
                fig = px.scatter(plot_df, x=x_column, y=y_column, 
                               title=get_message(f'{y_column} vs {x_column}', f'{y_column} vs {x_column}'))
                # Y축 설정 - 날짜 타입 고려
                if is_y_date:
                    fig.update_yaxes(title_text=y_column, type='date', autorange=True)
                else:
                    fig.update_yaxes(title_text=y_column, autorange=True)
                # X축 설정
                if is_x_date:
                    fig.update_xaxes(title_text=x_column, type='date')
                else:
                    fig.update_xaxes(title_text=x_column)
            
            elif chart_type == 'pie':
                print(f"\n파이 차트 생성 중...")
                
                if y_column:
                    # Y축이 있는 경우: 카테고리별 값 합계
                    pie_data = plot_df.groupby(x_column, as_index=False)[y_column].sum()
                    print(f"파이 차트 데이터: {len(pie_data)} 카테고리")
                    print(f"파이 데이터:\n{pie_data}")
                    fig = px.pie(pie_data, names=x_column, values=y_column, 
                               title=get_message(f'{y_column} 분포', f'{y_column} Distribution'))
                else:
                    # Y축이 없는 경우: 카테고리별 빈도수 계산
                    pie_data = plot_df[x_column].value_counts().reset_index()
                    pie_data.columns = [x_column, 'count']
                    print(f"파이 차트 데이터 (빈도수): {len(pie_data)} 카테고리")
                    print(f"파이 데이터:\n{pie_data}")
                    fig = px.pie(pie_data, names=x_column, values='count', 
                               title=get_message(f'{x_column} 분포', f'{x_column} Distribution'))

            
            elif chart_type == 'histogram':
                print(f"\n히스토그램 생성 중...")
                fig = px.histogram(plot_df, x=x_column, 
                                 title=get_message(f'{x_column} 분포', f'{x_column} Distribution'),
                                 nbins=20)
                fig.update_xaxes(title_text=x_column)
                fig.update_yaxes(title_text=get_message('빈도', 'Frequency'))
            
            else:
                return jsonify({'error': get_message('지원하지 않는 차트 유형입니다.', 'Unsupported chart type.')}), 400
            
            # 차트 레이아웃 개선
            fig.update_layout(
                font=dict(size=12),
                hovermode='closest',
                showlegend=True,
                height=500,
                margin=dict(l=70, r=50, t=80, b=70),
                xaxis=dict(fixedrange=False, gridcolor='#eef1f6', layer='below traces'),
                yaxis=dict(fixedrange=False, gridcolor='#eef1f6', layer='below traces'),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            
            # Plotly 자체 직렬화 사용 (프런트엔드 plotly.js 3.x가 base64 배열을 그대로 처리)
            graphJSON = fig.to_json()

            return jsonify({'chart': graphJSON})
        
        except Exception:
            logger.exception("차트 생성 오류: dataset_id=%s, chart_type=%s", dataset_id, chart_type)
            return jsonify({'error': get_message('차트 생성에 실패했습니다.', 'Chart creation failed.')}), 400

    except HTTPException:
        # get_or_404 등 Flask가 만든 응답 코드는 그대로 전달한다.
        raise
    except Exception:
        logger.exception("차트 API 처리 중 예상하지 못한 오류: %s", request.path)
        return jsonify({'error': get_message('서버 오류로 차트를 생성하지 못했습니다.',
                                             'The chart could not be generated due to a server error.')}), 500

# 템플릿 기반 시각화 - 메인 페이지
@app.route('/template')
@login_required
def template_dashboard():
    # 사용자의 템플릿 기반 데이터셋 조회
    template_datasets = Dataset.query.filter_by(
        user_id=current_user.id,
        is_template=True
    ).order_by(Dataset.uploaded_at.desc()).all()
    return render_template('template_dashboard.html', datasets=template_datasets)

# 템플릿 샘플 다운로드
@app.route('/template/download_sample')
@login_required
def download_sample_template():
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from flask import send_file
    
    # 새 워크북 생성
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Data"
    
    # 헤더 스타일
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # 헤더 작성
    headers = ["날짜", "지역", "제품", "카테고리", "판매량", "매출액", "비용"]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # 샘플 데이터 생성
    from datetime import datetime, timedelta
    import random
    
    regions = ["서울", "경기", "부산", "대구", "인천"]
    products = ["노트북", "태블릿", "스마트폰", "이어폰", "키보드"]
    categories = ["전자기기", "전자기기", "전자기기", "액세서리", "액세서리"]
    
    start_date = datetime(2024, 1, 1)
    
    row = 2
    for day in range(90):  # 90일치 데이터
        current_date = start_date + timedelta(days=day)
        for _ in range(random.randint(3, 8)):  # 하루에 3-8건
            region = random.choice(regions)
            product_idx = random.randint(0, len(products)-1)
            product = products[product_idx]
            category = categories[product_idx]
            quantity = random.randint(1, 20)
            price = random.randint(50000, 2000000)
            revenue = quantity * price
            cost = int(revenue * random.uniform(0.6, 0.8))
            
            ws.cell(row=row, column=1, value=current_date.strftime("%Y-%m-%d"))
            ws.cell(row=row, column=2, value=region)
            ws.cell(row=row, column=3, value=product)
            ws.cell(row=row, column=4, value=category)
            ws.cell(row=row, column=5, value=quantity)
            ws.cell(row=row, column=6, value=revenue)
            ws.cell(row=row, column=7, value=cost)
            row += 1
    
    # 컬럼 너비 조정
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 10
    ws.column_dimensions['F'].width = 15
    ws.column_dimensions['G'].width = 15
    
    # 메모리에 저장
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='sales_template_sample.xlsx'
    )

# 템플릿 업로드 및 자동 분석
@app.route('/template/upload', methods=['POST'])
@login_required
def upload_template():
    if 'file' not in request.files:
        flash_msg('no_file_selected', 'danger')
        return redirect(url_for('template_dashboard'))

    file = request.files['file']

    if file.filename == '':
        flash_msg('no_file_selected', 'danger')
        return redirect(url_for('template_dashboard'))

    if file and allowed_file(file.filename):
        try:
            filepath, timestamp = save_upload(file, current_user.id, 'template')
        except OSError:
            logger.exception("템플릿 파일 저장 실패: %s", file.filename)
            flash_msg('save_failed', 'danger')
            return redirect(url_for('template_dashboard'))

        try:
            df = pd.read_excel(filepath)
            dataset = create_dataset_with_records(
                df,
                name=f"Template Analysis {timestamp}",
                description="Template-based automated analysis",
                filename=file.filename,
                file_path=filepath,
                user_id=current_user.id,
                is_template=True
            )
            db.session.commit()
            flash_msg('template_uploaded', 'success')
            return redirect(url_for('view_template_analysis', dataset_id=dataset.id))

        except Exception:
            db.session.rollback()
            logger.exception("템플릿 업로드 실패: %s", filepath)
            flash_msg('process_failed', 'danger')
            remove_file(filepath)
            return redirect(url_for('template_dashboard'))
    else:
        flash_msg('invalid_file_format', 'danger')
        return redirect(url_for('template_dashboard'))

# 템플릿 기반 자동 분석 뷰
@app.route('/template/analysis/<int:dataset_id>')
@login_required
def view_template_analysis(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)

    denied = _deny_if_not_owner(dataset, 'template_dashboard')
    if denied:
        return denied

    df = load_dataset_dataframe(dataset_id)
    
    # 자동으로 차트 생성 (생성 실패는 사용자에게 알린다)
    failures = []
    charts   = generate_template_charts(df, failures)
    metrics  = calculate_metrics(df, failures)
    insights = generate_insights(df, failures)
    _flash_analysis_failures(failures)

    return render_template('template_result.html',
                         dataset=dataset,
                         charts=charts,
                         metrics=metrics,
                         insights=insights,
                         data=df.head(100).to_dict('records'),
                         columns=df.columns.tolist())

def _detect_template_type(df):
    cols = set(df.columns)
    if 'Crop_Type' in cols or 'Crop_Yield_kg' in cols:
        return 'crop'
    if 'Channel' in cols and 'Impressions' in cols:
        return 'marketing'
    if 'Segment' in cols and 'Age' in cols:
        return 'customer'
    if 'Revenue' in cols or 'Date' in cols:
        return 'sales'
    return 'generic'

# 템플릿 차트 자동 생성 함수
def generate_template_charts(df, failures=None):
    charts = {}
    common_layout = dict(BASE_LAYOUT)

    try:
        ttype = _detect_template_type(df)
        print(f"템플릿 유형 감지: {ttype}, 컬럼: {df.columns.tolist()}")

        if ttype == 'sales':
            _charts_sales(df, charts, common_layout)
        elif ttype == 'crop':
            _charts_crop(df, charts, common_layout)
        elif ttype == 'marketing':
            _charts_marketing(df, charts, common_layout)
        elif ttype == 'customer':
            _charts_customer(df, charts, common_layout)
        else:
            _charts_generic(df, charts, common_layout)

    except Exception as exc:
        _record_failure(failures, STAGE_CHARTS, exc)

    return charts


def _charts_sales(df, charts, layout):
    col_date, col_revenue, col_region, col_product, col_category, col_quantity, col_cost = \
        resolve_columns(df, '날짜', '매출액', '지역', '제품', '카테고리', '판매량', '비용')

    if col_date:
        df[col_date] = pd.to_datetime(df[col_date], errors='coerce')

    # 1. 월별 매출 vs 비용 비교 (그룹 바 or 라인)
    if col_date and col_revenue:
        df['_month'] = df[col_date].dt.to_period('M').astype(str)
        if col_cost:
            monthly = group_sum(df, '_month', [col_revenue, col_cost])
            fig = grouped_bar(
                monthly['_month'].tolist(),
                [('매출', monthly[col_revenue].tolist(), '#0d6efd'),
                 ('비용', monthly[col_cost].tolist(), '#dc3545')],
                title='월별 매출 vs 비용', layout=layout, xaxis_title='월'
            )
        else:
            monthly = group_sum(df, '_month', col_revenue)
            fig = line_trend(monthly, '_month', col_revenue, '월별 매출 추이',
                             layout=layout, color='#0d6efd')
        charts['daily_sales'] = fig.to_json()

    # 2. 지역별 매출 (수평 바, 내림차순)
    if col_region and col_revenue:
        data = group_sum(df, col_region, col_revenue, sort_by=col_revenue)
        fig = horizontal_bar(data, col_revenue, col_region, '지역별 매출 (내림차순)', layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 제품별 판매 비율 (도넛 차트)
    if col_product and col_revenue:
        data = group_sum(df, col_product, col_revenue, sort_by=col_revenue, ascending=False)
        fig = pie_chart(data, col_product, col_revenue, '제품별 매출 비중', layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 카테고리별 매출 + 판매량 (이중축 바)
    if col_category and col_revenue:
        value_cols = [col_revenue, col_quantity] if col_quantity else [col_revenue]
        data = group_sum(df, col_category, value_cols, sort_by=col_revenue, ascending=False)
        fig = px.bar(data, x=col_category, y=col_revenue,
                     title='카테고리별 매출', color=col_category,
                     text_auto='.2s')
        fig.update_layout(**layout)
        charts['category_sales'] = fig.to_json()

    # 5. 판매량 vs 매출액 (제품별 색상 산점도)
    if col_quantity and col_revenue:
        color_arg = col_product if col_product else col_category
        fig = go_scatter(df, col_quantity, col_revenue, color_col=color_arg,
                         title='판매량 vs 매출액',
                         x_label='판매량', y_label='매출액', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 제품별 이익률 (수평 바)
    if col_product and col_revenue and col_cost:
        data = group_sum(df, col_product, [col_revenue, col_cost])
        data = add_ratio_column(data, '이익률(%)', col_revenue, col_cost, mode='margin')
        data = data.sort_values('이익률(%)')
        fig = horizontal_bar(data, '이익률(%)', col_product, '제품별 이익률(%)',
                             layout=layout, color_scale='RdYlGn')
        charts['daily_quantity'] = fig.to_json()
    elif col_date and col_quantity:
        group_col = '_month' if '_month' in df.columns else col_date
        daily = group_sum(df, group_col, col_quantity)
        fig = line_trend(daily, group_col, col_quantity, '월별 판매량 추이',
                         layout=layout, color='#198754')
        charts['daily_quantity'] = fig.to_json()


def _charts_crop(df, charts, layout):
    col_crop, col_yield, col_climate, col_soil, col_rain, col_temp, col_fert = \
        resolve_columns(df, '작물', '수확량', '기후', '토양', '강수량', '온도', '비료')

    # 1. 작물별 수확량 분포 (go.Box — px.box color 버그 우회)
    if col_crop and col_yield:
        fig = distribution_by_group(df, col_crop, col_yield, '작물 유형별 수확량 분포',
                                    layout=layout, yaxis_title='수확량 (kg)')
        charts['daily_sales'] = fig.to_json()

    # 2. 기후 × 토양 조합별 평균 수확량 (히트맵)
    if col_climate and col_soil and col_yield:
        pivot = df.groupby([col_climate, col_soil])[col_yield].mean().reset_index()
        pivot_table = pivot.pivot(index=col_climate, columns=col_soil, values=col_yield)
        fig = go.Figure(data=go.Heatmap(
            z=pivot_table.values.tolist(),
            x=pivot_table.columns.tolist(),
            y=pivot_table.index.tolist(),
            colorscale='YlGn',
            text=[[f'{v:.0f}' for v in row] for row in pivot_table.values],
            texttemplate='%{text}',
            hovertemplate='기후: %{y}<br>토양: %{x}<br>수확량: %{z:.0f}kg<extra></extra>'
        ))
        fig.update_layout(title='기후 × 토양 조합별 평균 수확량', **layout)
        charts['region_sales'] = fig.to_json()
    elif col_climate and col_yield:
        fig = distribution_by_group(df, col_climate, col_yield, '기후별 수확량 분포',
                                    layout=layout, yaxis_title='수확량 (kg)')
        charts['region_sales'] = fig.to_json()

    # 3. 작물별 데이터 구성 비율 (도넛)
    if col_crop:
        counts = value_counts_frame(df, col_crop)
        fig = pie_chart(counts, col_crop, 'count', '작물 유형 구성 비율', layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 토양 유형별 수확량 분포 (go.Violin — px.violin color 버그 우회)
    if col_soil and col_yield:
        fig = distribution_by_group(df, col_soil, col_yield, '토양 유형별 수확량 분포',
                                    layout=layout, kind='violin', yaxis_title='수확량 (kg)')
        charts['category_sales'] = fig.to_json()

    # 5. 강수량 vs 수확량 (작물별 색상, 비료량 = 마커 크기)
    if col_rain and col_yield:
        fig = go_scatter(df, col_rain, col_yield, color_col=col_crop,
                         size_col=col_fert, size_max=18,
                         title='강수량 vs 수확량 (마커 크기 = 비료량)',
                         x_label='강수량 (mm)', y_label='수확량 (kg)', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 온도 vs 수확량 (작물별 색상)
    if col_temp and col_yield:
        fig = go_scatter(df, col_temp, col_yield, color_col=col_crop,
                         title='기온 vs 수확량',
                         x_label='기온 (°C)', y_label='수확량 (kg)', layout=layout)
        fig.update_layout(**layout)
        fig.update_traces(marker=dict(size=9, opacity=0.7))
        charts['daily_quantity'] = fig.to_json()


def _charts_marketing(df, charts, layout):
    col_channel, col_revenue, col_budget, col_clicks, col_conv, col_impr, col_date = \
        resolve_columns(df, '채널', '매출액', '예산', '클릭', '전환', '노출', '날짜')

    if col_date:
        add_month_column(df, col_date)

    # 1. 월별 매출 + 예산 추이 (그룹 바)
    if '_month' in df.columns and col_revenue and col_budget:
        monthly = group_sum(df, '_month', [col_revenue, col_budget])
        fig = grouped_bar(
            monthly['_month'].tolist(),
            [('매출', monthly[col_revenue].tolist(), '#0d6efd'),
             ('예산', monthly[col_budget].tolist(), '#adb5bd')],
            title='월별 매출 vs 예산', layout=layout, xaxis_title='월'
        )
        charts['daily_sales'] = fig.to_json()
    elif '_month' in df.columns and col_revenue:
        monthly = group_sum(df, '_month', col_revenue)
        fig = line_trend(monthly, '_month', col_revenue, '월별 매출 추이', layout=layout)
        charts['daily_sales'] = fig.to_json()

    # 2. 채널별 ROI (수평 바 — ROI% = (매출-예산)/예산*100)
    if col_channel and col_revenue and col_budget:
        agg = group_sum(df, col_channel, [col_revenue, col_budget])
        agg = add_ratio_column(agg, 'ROI(%)', col_revenue, col_budget, mode='gain')
        agg = agg.sort_values('ROI(%)')
        fig = horizontal_bar(agg, 'ROI(%)', col_channel, '채널별 ROI (%)',
                             layout=layout, color_scale='RdYlGn',
                             text='ROI(%)', texttemplate='%{text:.1f}%')
        charts['region_sales'] = fig.to_json()
    elif col_channel and col_revenue:
        data = group_sum(df, col_channel, col_revenue, sort_by=col_revenue)
        fig = horizontal_bar(data, col_revenue, col_channel, '채널별 총 매출', layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 채널별 캠페인 예산 비중 (도넛)
    if col_channel and col_budget:
        data = group_sum(df, col_channel, col_budget)
        fig = pie_chart(data, col_channel, col_budget, '채널별 예산 배분', layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 채널별 전환율 (전환/클릭 × 100, 수평 바)
    if col_channel and col_conv and col_clicks:
        agg = group_sum(df, col_channel, [col_conv, col_clicks])
        agg = add_ratio_column(agg, '전환율(%)', col_conv, col_clicks, digits=2)
        agg = agg.sort_values('전환율(%)')
        fig = horizontal_bar(agg, '전환율(%)', col_channel, '채널별 전환율 (%)',
                             layout=layout, color_scale='Teal',
                             text='전환율(%)', texttemplate='%{text:.2f}%')
        charts['category_sales'] = fig.to_json()
    elif col_channel and col_conv:
        data = group_sum(df, col_channel, col_conv, sort_by=col_conv)
        fig = horizontal_bar(data, col_conv, col_channel, '채널별 총 전환수',
                             layout=layout, color_scale='Teal')
        charts['category_sales'] = fig.to_json()

    # 5. 예산 vs 매출 버블 차트 (채널 색상, 노출수 = 크기)
    if col_budget and col_revenue:
        fig = go_scatter(df, col_budget, col_revenue, color_col=col_channel,
                         size_col=col_impr, size_max=25,
                         title='예산 vs 매출 (버블 크기 = 노출수)',
                         x_label='예산', y_label='매출액', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 마케팅 퍼널 (노출 → 클릭 → 전환, 채널별 집계)
    if col_channel and col_impr and col_clicks and col_conv:
        agg = group_sum(df, col_channel, [col_impr, col_clicks, col_conv])
        fig = go.Figure()
        for i, row in agg.iterrows():
            fig.add_trace(go.Funnel(
                name=row[col_channel],
                y=['노출', '클릭', '전환'],
                x=[row[col_impr], row[col_clicks], row[col_conv]],
                marker=dict(color=QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)])
            ))
        fig.update_layout(title='채널별 마케팅 퍼널', **layout)
        charts['daily_quantity'] = fig.to_json()
    elif col_clicks and col_conv:
        fig = go_scatter(df, col_clicks, col_conv, color_col=col_channel,
                         title='클릭수 vs 전환수',
                         x_label='클릭수', y_label='전환수', layout=layout)
        charts['daily_quantity'] = fig.to_json()


def _charts_customer(df, charts, layout):
    col_seg, col_age, col_gender, col_income, col_purch, col_value = \
        resolve_columns(df, '세그먼트', '나이', '성별', '소득', '구매횟수', '구매금액')
    col_recency = 'Last_Purchase_Days' if 'Last_Purchase_Days' in df.columns else None

    # 1. 연령 × 세그먼트 분포 (go.Histogram으로 직접 — px.histogram color 버그 우회)
    if col_age:
        group_col = col_seg if col_seg else col_gender
        title = '고객 연령대 분포 (세그먼트별)' if group_col else '고객 연령 분포'
        fig = histogram_by_group(df, col_age, group_col, title,
                                 layout=layout, xaxis_title='나이')
        charts['daily_sales'] = fig.to_json()

    # 2. 세그먼트별 총 구매금액 (수평 바, 내림차순)
    if col_seg and col_value:
        data = group_sum(df, col_seg, col_value, sort_by=col_value)
        fig = horizontal_bar(data, col_value, col_seg, '세그먼트별 총 구매금액',
                             layout=layout, text_auto='.2s')
        charts['region_sales'] = fig.to_json()
    elif col_seg:
        counts = value_counts_frame(df, col_seg)
        fig = simple_bar(counts, col_seg, 'count', '세그먼트별 고객 수', layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 성별 구매금액 비중 (도넛)
    if col_gender and col_value:
        data = group_sum(df, col_gender, col_value)
        fig = pie_chart(data, col_gender, col_value, '성별 구매금액 비중', layout=layout,
                        color_sequence=px.colors.qualitative.Pastel)
        charts['product_distribution'] = fig.to_json()
    elif col_gender:
        counts = value_counts_frame(df, col_gender)
        fig = pie_chart(counts, col_gender, 'count', '성별 비율', layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 세그먼트별 구매금액 분포 (go.Box — px.box color 버그 우회)
    if col_seg and col_value:
        fig = distribution_by_group(df, col_seg, col_value, '세그먼트별 구매금액 분포',
                                    layout=layout, yaxis_title='평균 구매금액')
        charts['category_sales'] = fig.to_json()

    # 5. 소득 vs 구매금액 (세그먼트 색상, 구매횟수 = 마커 크기)
    if col_income and col_value:
        color_arg = col_seg if col_seg else col_gender
        fig = go_scatter(df, col_income, col_value, color_col=color_arg,
                         size_col=col_purch, size_max=18,
                         title='소득 vs 구매금액 (마커 크기 = 구매횟수)',
                         x_label='소득', y_label='평균 구매금액', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 구매 주기 분포 (go.Histogram — px 버그 우회)
    if col_recency:
        fig = histogram_by_group(df, col_recency, col_seg,
                                 '마지막 구매 후 경과일 분포 (구매 주기)',
                                 layout=layout, nbins=20, xaxis_title='경과일 (일)')
        charts['daily_quantity'] = fig.to_json()
    elif col_age and col_purch:
        fig = go_scatter(df, col_age, col_purch,
                         color_col=col_seg if col_seg else None,
                         title='연령 vs 총 구매횟수',
                         x_label='나이', y_label='총 구매횟수', layout=layout)
        charts['daily_quantity'] = fig.to_json()


def _charts_generic(df, charts, layout):
    """알 수 없는 템플릿 — 숫자/범주형 컬럼으로 자동 차트 생성"""
    num_cols = df.select_dtypes(include='number').columns.tolist()
    cat_cols = df.select_dtypes(include='object').columns.tolist()

    if cat_cols and num_cols:
        data = group_sum(df, cat_cols[0], num_cols[0],
                         sort_by=num_cols[0], ascending=False).head(15)
        fig = px.bar(data, x=cat_cols[0], y=num_cols[0], title=f'{cat_cols[0]}별 {num_cols[0]}')
        fig.update_layout(**layout)
        charts['region_sales'] = fig.to_json()

    if len(num_cols) >= 2:
        fig = px.scatter(df, x=num_cols[0], y=num_cols[1], title=f'{num_cols[0]} vs {num_cols[1]}')
        fig.update_layout(**layout)
        charts['quantity_revenue'] = fig.to_json()

    if cat_cols:
        counts = value_counts_frame(df, cat_cols[0], top=10)
        fig = pie_chart(counts, cat_cols[0], 'count', f'{cat_cols[0]} 분포',
                        layout=layout, hole=None)
        charts['product_distribution'] = fig.to_json()

# 주요 지표 계산 함수 (4개 템플릿 전체 지원)
def calculate_metrics(df, failures=None):
    metrics = {}
    try:
        ttype = _detect_template_type(df)
        metrics['total_records'] = len(df)

        if ttype == 'sales':
            col_revenue, col_quantity, col_cost, col_product = \
                resolve_columns(df, '매출액', '판매량', '비용', '제품')
            if col_revenue:
                metrics['total_revenue'] = int(df[col_revenue].sum())
                metrics['avg_revenue']   = int(df[col_revenue].mean())
            if col_quantity:
                metrics['total_quantity'] = int(df[col_quantity].sum())
                metrics['avg_quantity']   = round(df[col_quantity].mean(), 1)
            if col_cost and col_revenue:
                profit = df[col_revenue].sum() - df[col_cost].sum()
                metrics['total_profit']  = int(profit)
                metrics['profit_margin'] = round(ratio_pct(profit, df[col_revenue].sum()), 1)
            if col_product:
                metrics['unique_products'] = df[col_product].nunique()

        elif ttype == 'crop':
            col_crop, col_yield, col_rain = resolve_columns(df, '작물', '수확량', '강수량')
            if col_yield:
                metrics['total_revenue'] = int(df[col_yield].sum())
                metrics['avg_revenue']   = int(df[col_yield].mean())
            if col_rain:
                metrics['total_quantity'] = int(df[col_rain].sum())
                metrics['avg_quantity']   = round(df[col_rain].mean(), 1)
            if col_crop:
                metrics['unique_products'] = df[col_crop].nunique()

        elif ttype == 'marketing':
            col_revenue, col_budget, col_conv = resolve_columns(df, '매출액', '예산', '전환')
            if col_revenue:
                metrics['total_revenue'] = int(df[col_revenue].sum())
                metrics['avg_revenue']   = int(df[col_revenue].mean())
            if col_budget and col_revenue:
                roi = gain_pct(df[col_revenue].sum(), df[col_budget].sum())
                metrics['total_profit']  = int(df[col_revenue].sum() - df[col_budget].sum())
                metrics['profit_margin'] = round(roi, 1)
            if col_conv:
                metrics['total_quantity'] = int(df[col_conv].sum())
                metrics['avg_quantity']   = round(df[col_conv].mean(), 1)

        elif ttype == 'customer':
            col_purch, col_value, col_seg = resolve_columns(df, '구매횟수', '구매금액', '세그먼트')
            if col_value:
                metrics['total_revenue'] = int(df[col_value].sum())
                metrics['avg_revenue']   = int(df[col_value].mean())
            if col_purch:
                metrics['total_quantity'] = int(df[col_purch].sum())
                metrics['avg_quantity']   = round(df[col_purch].mean(), 1)
            if col_seg:
                metrics['unique_products'] = df[col_seg].nunique()

    except Exception as exc:
        _record_failure(failures, STAGE_METRICS, exc)

    return metrics

# ── 차트별 인사이트 자동 생성 ──────────────────────────────────────
# TODO: 추후 Claude API 연동으로 교체 예정
# 각 chart_key → 분석 텍스트 반환 (template_result.html에서 카드 하단에 표시)
def generate_insights(df, failures=None):
    insights = {}
    try:
        ttype = _detect_template_type(df)
        if ttype == 'sales':
            insights.update(_insights_sales(df))
        elif ttype == 'crop':
            insights.update(_insights_crop(df))
        elif ttype == 'marketing':
            insights.update(_insights_marketing(df))
        elif ttype == 'customer':
            insights.update(_insights_customer(df))
    except Exception as exc:
        _record_failure(failures, STAGE_INSIGHTS, exc)
    return insights


def _insights_sales(df):
    ins = {}
    col_date, col_revenue, col_region, col_product, col_category, col_quantity, col_cost = \
        resolve_columns(df, '날짜', '매출액', '지역', '제품', '카테고리', '판매량', '비용')

    if col_date and col_revenue:
        df2 = df.copy()
        month_col = add_month_column(df2, col_date)
        monthly = df2.groupby(month_col)[col_revenue].sum()
        best_month = monthly.idxmax()
        worst_month = monthly.idxmin()
        growth = gain_pct(monthly.iloc[-1], monthly.iloc[0]) if len(monthly) > 1 else 0
        ins['daily_sales'] = (
            f"📈 최고 매출 월은 <strong>{best_month}</strong> "
            f"({int(monthly.max()):,}원), 최저는 <strong>{worst_month}</strong> ({int(monthly.min()):,}원)입니다. "
            f"전체 기간 동안 매출은 약 <strong>{growth:+.1f}%</strong> 변화했습니다."
        )

    if col_region and col_revenue:
        top, top_pct, by_region = top_share(df, col_region, col_revenue)
        ins['region_sales'] = (
            f"🏆 <strong>{top}</strong> 지역이 전체 매출의 <strong>{top_pct:.1f}%</strong>를 차지하며 1위입니다. "
            f"하위 지역과의 매출 차이는 {int(by_region.iloc[0] - by_region.iloc[-1]):,}원입니다."
        )

    if col_product and col_revenue:
        top, top_pct, by_prod = top_share(df, col_product, col_revenue)
        ins['product_distribution'] = (
            f"🥇 <strong>{top}</strong> 제품이 전체 매출의 <strong>{top_pct:.1f}%</strong>를 차지하는 핵심 제품입니다. "
            f"상위 2개 제품이 전체의 {ratio_pct(by_prod.iloc[:2].sum(), by_prod.sum()):.1f}%를 차지합니다."
        )

    if col_category and col_revenue:
        by_cat = group_agg(df, col_category, col_revenue)
        top = by_cat.index[0]
        ins['category_sales'] = (
            f"📦 <strong>{top}</strong> 카테고리가 가장 높은 매출을 기록했습니다. "
            f"카테고리 간 매출 편차는 {int(by_cat.std()):,}원으로, "
            f"{'편차가 크므로 집중 육성 카테고리를 검토하세요.' if by_cat.std() > by_cat.mean() * 0.3 else '카테고리별 매출이 비교적 균등합니다.'}"
        )

    if col_quantity and col_revenue:
        corr = correlation(df, col_quantity, col_revenue)
        ins['quantity_revenue'] = (
            f"📊 판매량과 매출액의 상관계수는 <strong>{corr:.2f}</strong>입니다. "
            f"{'강한 양의 상관관계로, 판매량 증가가 매출 향상으로 이어집니다.' if corr > 0.7 else '판매량 외 단가·할인율 등 다른 요인도 매출에 영향을 미칩니다.'}"
        )

    if col_product and col_revenue and col_cost:
        df2 = df.groupby(col_product)[[col_revenue, col_cost]].sum()
        df2 = add_ratio_column(df2, 'margin', col_revenue, col_cost, mode='margin', digits=10)
        best = df2['margin'].idxmax()
        worst = df2['margin'].idxmin()
        ins['daily_quantity'] = (
            f"💰 이익률이 가장 높은 제품은 <strong>{best}</strong> ({df2.loc[best, 'margin']:.1f}%), "
            f"가장 낮은 제품은 <strong>{worst}</strong> ({df2.loc[worst, 'margin']:.1f}%)입니다. "
            f"저마진 제품의 원가 절감 또는 가격 재조정을 검토하세요."
        )
    return ins


def _insights_crop(df):
    ins = {}
    col_crop, col_yield, col_climate, col_soil, col_rain, col_temp = \
        resolve_columns(df, '작물', '수확량', '기후', '토양', '강수량', '온도')

    if col_crop and col_yield:
        by_crop = group_agg(df, col_crop, col_yield, how='mean')
        top = by_crop.index[0]
        low = by_crop.index[-1]
        ins['daily_sales'] = (
            f"🌾 <strong>{top}</strong>이 평균 {int(by_crop.iloc[0]):,}kg으로 가장 높은 수확량을 보입니다. "
            f"<strong>{low}</strong>와의 차이는 {int(by_crop.iloc[0] - by_crop.iloc[-1]):,}kg이며, "
            f"박스플롯의 수염 길이가 클수록 수확량 변동성이 높습니다."
        )

    if col_climate and col_soil and col_yield:
        pivot = df.groupby([col_climate, col_soil])[col_yield].mean()
        best_idx = pivot.idxmax()
        ins['region_sales'] = (
            f"🌍 기후 <strong>{best_idx[0]}</strong> × 토양 <strong>{best_idx[1]}</strong> 조합에서 "
            f"평균 수확량이 {int(pivot.max()):,}kg으로 가장 높습니다. "
            f"히트맵에서 진한 녹색 조합이 최적 재배 조건입니다."
        )

    if col_crop:
        counts = df[col_crop].value_counts()
        dominant = counts.index[0]
        ins['product_distribution'] = (
            f"📋 데이터셋에서 <strong>{dominant}</strong>이 전체의 {ratio_pct(counts.iloc[0], len(df)):.1f}%를 차지합니다. "
            f"균형 잡힌 비교 분석을 위해 각 작물별 데이터 수가 균등한지 확인하세요."
        )

    if col_soil and col_yield:
        by_soil = group_agg(df, col_soil, col_yield, how='median')
        top = by_soil.index[0]
        ins['category_sales'] = (
            f"🌱 <strong>{top}</strong> 토양이 중앙값 기준으로 수확량이 가장 높습니다. "
            f"바이올린 플롯의 폭이 넓을수록 해당 토양에서의 수확량 편차가 크며, "
            f"재배 환경 관리의 일관성을 높일 필요가 있습니다."
        )

    if col_rain and col_yield:
        corr = correlation(df, col_rain, col_yield)
        ins['quantity_revenue'] = (
            f"💧 강수량과 수확량의 상관계수: <strong>{corr:.2f}</strong>. "
            f"{'강수량이 수확량에 큰 영향을 미치므로 관개 시스템이 중요합니다.' if corr > 0.5 else '강수량 외 다른 요인(비료, 온도 등)도 수확량에 복합적으로 작용합니다.'} "
            f"마커 크기(비료량)가 클수록 수확량 향상 효과를 확인하세요."
        )

    if col_temp and col_yield:
        corr = correlation(df, col_temp, col_yield)
        opt_temp = df.groupby(pd.cut(df[col_temp], bins=5))[col_yield].mean().idxmax()
        ins['daily_quantity'] = (
            f"🌡️ 기온과 수확량의 상관계수: <strong>{corr:.2f}</strong>. "
            f"수확량이 가장 높은 온도 구간은 <strong>{opt_temp}</strong>°C입니다. "
            f"작물별로 최적 온도 범위가 다르므로 색상별 군집을 확인하세요."
        )
    return ins


def _insights_marketing(df):
    ins = {}
    col_channel, col_revenue, col_budget, col_clicks, col_conv, col_impr = \
        resolve_columns(df, '채널', '매출액', '예산', '클릭', '전환', '노출')

    if col_revenue and col_budget:
        df2 = df.copy()
        df2[col_revenue] = pd.to_numeric(df2[col_revenue], errors='coerce')
        df2[col_budget]  = pd.to_numeric(df2[col_budget], errors='coerce')
        total_roi = gain_pct(df2[col_revenue].sum(), df2[col_budget].sum())

        col_date = resolve_column(df, '날짜')
        if col_date:
            month_col = add_month_column(df2, col_date)
            monthly_rev = df2.groupby(month_col)[col_revenue].sum()
            best_m = monthly_rev.idxmax()
            ins['daily_sales'] = (
                f"📅 전체 평균 ROI는 <strong>{total_roi:.1f}%</strong>입니다. "
                f"<strong>{best_m}</strong>에 최대 매출 {int(monthly_rev.max()):,}원을 기록했습니다. "
                f"예산 대비 매출 막대가 큰 달의 캠페인 전략을 분석하세요."
            )

    if col_channel and col_revenue and col_budget:
        agg = df.groupby(col_channel)[[col_revenue, col_budget]].sum()
        agg = add_ratio_column(agg, 'roi', col_revenue, col_budget, mode='gain', digits=10)
        best_ch = agg['roi'].idxmax()
        worst_ch = agg['roi'].idxmin()
        ins['region_sales'] = (
            f"🎯 ROI 최고 채널: <strong>{best_ch}</strong> ({agg.loc[best_ch, 'roi']:.1f}%), "
            f"최저: <strong>{worst_ch}</strong> ({agg.loc[worst_ch, 'roi']:.1f}%). "
            f"{'음수 ROI 채널은 예산 조정 또는 캠페인 개선이 필요합니다.' if agg['roi'].min() < 0 else '모든 채널이 양의 ROI를 기록 중입니다.'}"
        )

    if col_channel and col_budget:
        by_ch = df.groupby(col_channel)[col_budget].sum()
        top_ch = by_ch.idxmax()
        top_pct = ratio_pct(by_ch.max(), by_ch.sum())
        ins['product_distribution'] = (
            f"💸 예산의 <strong>{top_pct:.1f}%</strong>가 <strong>{top_ch}</strong> 채널에 집중되어 있습니다. "
            f"{'채널 다변화를 통해 리스크 분산을 고려하세요.' if top_pct > 40 else '채널별 예산 배분이 비교적 균등합니다.'}"
        )

    if col_channel and col_conv and col_clicks:
        agg = df.groupby(col_channel)[[col_conv, col_clicks]].sum()
        agg = add_ratio_column(agg, 'cvr', col_conv, col_clicks, digits=10)
        best = agg['cvr'].idxmax()
        avg_cvr = agg['cvr'].mean()
        ins['category_sales'] = (
            f"✅ 전환율 1위 채널: <strong>{best}</strong> ({agg.loc[best, 'cvr']:.2f}%). "
            f"전체 평균 전환율은 {avg_cvr:.2f}%이며, "
            f"전환율이 낮은 채널은 랜딩 페이지 및 타겟팅 최적화를 검토하세요."
        )

    if col_budget and col_revenue:
        corr = correlation(df, col_budget, col_revenue, numeric=True)
        ins['quantity_revenue'] = (
            f"💰 예산-매출 상관계수: <strong>{corr:.2f}</strong>. "
            f"{'예산 투자가 매출로 효율적으로 전환되고 있습니다.' if corr > 0.7 else '예산 증가가 반드시 매출 증가로 이어지지 않습니다. 캠페인 품질을 점검하세요.'} "
            f"버블 크기(노출수)가 크지만 매출이 낮은 캠페인은 메시지 효과를 재검토하세요."
        )

    if col_channel and col_impr and col_clicks and col_conv:
        agg = df.groupby(col_channel)[[col_impr, col_clicks, col_conv]].sum()
        agg = add_ratio_column(agg, 'ctr', col_clicks, col_impr, digits=10)
        best_ctr = agg['ctr'].idxmax()
        ins['daily_quantity'] = (
            f"📣 퍼널 분석: 클릭률(CTR) 최고 채널은 <strong>{best_ctr}</strong> ({agg.loc[best_ctr, 'ctr']:.2f}%). "
            f"노출 대비 전환이 낮은 채널은 클릭 후 경험(UX, 오퍼) 개선이 필요합니다. "
            f"퍼널 각 단계의 이탈률을 분석해 병목 구간을 파악하세요."
        )
    return ins


def _insights_customer(df):
    ins = {}
    col_seg, col_age, col_gender, col_income, col_purch, col_value = \
        resolve_columns(df, '세그먼트', '나이', '성별', '소득', '구매횟수', '구매금액')
    col_recency = 'Last_Purchase_Days' if 'Last_Purchase_Days' in df.columns else None

    if col_age:
        avg_age = df[col_age].mean()
        mode_range = pd.cut(df[col_age], bins=[0,20,30,40,50,60,100]).value_counts().idxmax()
        ins['daily_sales'] = (
            f"👤 평균 고객 연령: <strong>{avg_age:.1f}세</strong>, "
            f"가장 많은 연령대: <strong>{mode_range}</strong>. "
            f"핵심 연령대에 맞는 마케팅 메시지와 채널 전략을 수립하세요."
        )

    if col_seg and col_value:
        top, top_pct, by_seg = top_share(df, col_seg, col_value)
        ins['region_sales'] = (
            f"💼 <strong>{top}</strong> 세그먼트가 총 구매금액의 <strong>{top_pct:.1f}%</strong>를 차지합니다. "
            f"고가치 세그먼트 유지에 집중하고, 저가치 세그먼트의 업셀링 기회를 모색하세요."
        )

    if col_gender and col_value:
        by_gender = df.groupby(col_gender)[col_value].sum()
        dominant = by_gender.idxmax()
        pct = ratio_pct(by_gender.max(), by_gender.sum())
        ins['product_distribution'] = (
            f"⚖️ <strong>{dominant}</strong> 고객이 전체 구매금액의 <strong>{pct:.1f}%</strong>를 차지합니다. "
            f"{'성별 구매 격차가 크므로 비중이 낮은 성별 대상 프로모션을 검토하세요.' if pct > 60 else '성별 구매금액 비중이 비교적 균등합니다.'}"
        )

    if col_seg and col_value:
        by_seg = df.groupby(col_seg)[col_value]
        cv = (by_seg.std() / by_seg.mean()).sort_values(ascending=False)
        high_var = cv.index[0]
        ins['category_sales'] = (
            f"📊 <strong>{high_var}</strong> 세그먼트 내 구매금액 편차가 가장 큽니다 (CV: {cv.iloc[0]:.2f}). "
            f"박스플롯에서 이상치(outlier)가 많은 세그먼트는 VIP 고객과 일반 고객이 혼재되어 있습니다. "
            f"세분화된 개인화 마케팅이 효과적입니다."
        )

    if col_income and col_value:
        corr = correlation(df, col_income, col_value, numeric=True)
        ins['quantity_revenue'] = (
            f"💳 소득-구매금액 상관계수: <strong>{corr:.2f}</strong>. "
            f"{'소득이 높을수록 구매금액도 높아 프리미엄 상품 전략이 유효합니다.' if corr > 0.5 else '소득과 구매금액의 상관이 낮습니다. 가격 감도보다 다른 요인(선호도, 브랜드)이 중요합니다.'} "
            f"마커 크기(구매횟수)가 클수록 충성 고객임을 나타냅니다."
        )

    if col_recency:
        avg_days = df[col_recency].mean()
        churned_pct = ratio_pct((df[col_recency] > 90).sum(), len(df))
        ins['daily_quantity'] = (
            f"⏰ 평균 마지막 구매 후 경과일: <strong>{avg_days:.1f}일</strong>. "
            f"90일 이상 미구매 고객 비율: <strong>{churned_pct:.1f}%</strong>. "
            f"{'이탈 위험 고객 비중이 높습니다. 재활성화 캠페인을 즉시 실행하세요.' if churned_pct > 30 else '고객 구매 주기가 양호합니다. 재구매 유도 타이밍을 최적화하세요.'}"
        )
    elif col_age and col_purch:
        corr = correlation(df, col_age, col_purch, numeric=True)
        ins['daily_quantity'] = (
            f"🔄 연령-구매횟수 상관계수: <strong>{corr:.2f}</strong>. "
            f"{'연령이 높을수록 구매 충성도가 높습니다.' if corr > 0.3 else '연령과 구매횟수의 상관이 낮습니다. 세그먼트 색상별로 구매 패턴의 차이를 확인하세요.'}"
        )
    return ins


# 데이터셋 삭제
@app.route('/dataset/<int:dataset_id>/delete', methods=['POST'])
@login_required
def delete_dataset(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash(get_message('접근 권한이 없습니다.', 'Access denied.'), 'danger')
        return redirect(url_for('dashboard'))
    
    if os.path.exists(dataset.file_path):
        os.remove(dataset.file_path)
    
    db.session.delete(dataset)
    db.session.commit()
    
    flash(get_message('데이터셋이 삭제되었습니다.', 'Dataset deleted successfully.'), 'success')
    return redirect(url_for('dashboard'))


####################
# ================================
# OCR 문서 스캔 라우트
# ================================

@app.route('/ocr/scan')
@login_required
def ocr_scan():
    """OCR 스캔 화면"""
    return render_template('ocr_scan.html')

@app.route('/ocr/upload', methods=['POST'])
@login_required
def ocr_upload():
    """OCR 파일 업로드 및 처리"""
    try:
        # 파일 확인
        if 'file' not in request.files:
            flash('파일이 없습니다.' if session.get('language') == 'ko' else 'No file uploaded.', 'danger')
            return redirect(url_for('ocr_scan'))
        
        file = request.files['file']
        
        if file.filename == '':
            flash('파일이 선택되지 않았습니다.' if session.get('language') == 'ko' else 'No file selected.', 'danger')
            return redirect(url_for('ocr_scan'))
        
        # 허용된 확장자 확인
        allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}
        if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            flash('지원하지 않는 파일 형식입니다. (PNG, JPG, PDF만 가능)' if session.get('language') == 'ko' else 'Unsupported file format. (PNG, JPG, PDF only)', 'danger')
            return redirect(url_for('ocr_scan'))
        
        filepath, _ = save_upload(file, 'ocr')
        unique_filename = os.path.basename(filepath)

        print(f"✅ 파일 저장: {filepath}")
        
        # OCR 세션 생성
        ocr_session = OCRSession(
            user_id=current_user.id,
            filename=unique_filename,
            file_path=filepath,
            status='processing'
        )
        db.session.add(ocr_session)
        db.session.commit()
        
        print(f"✅ OCR 세션 생성: {ocr_session.id}")
        
        # OCR 처리
        from src.ocr_utils import process_ocr_document
        
        try:
            # 전처리 옵션 (사용되지 않지만 호환성을 위해 받음)
            preprocess = request.form.get('denoise') == 'on'
            
            # OCR 실행 - 딕셔너리 반환
            result = process_ocr_document(filepath, preprocess=preprocess)
            
            # 성공 여부 확인
            if result['success']:
                df = result['data']  # DataFrame 가져오기
                
                # NaN → None 으로 정리해 JSON 직렬화 오류 방지
                data = dataframe_rows(df)
                columns = df.columns.tolist()

                # 세션에 저장
                ocr_session.extracted_data = {
                    'data': data,
                    'columns': columns,
                    'rows': len(data),
                    'method': result.get('method', 'unknown')
                }
                ocr_session.status = 'completed'
                db.session.commit()
                
                print(f"✅ OCR 완료: {len(data)}개 행, {len(columns)}개 컬럼")
                
                return redirect(url_for('ocr_verify', session_id=ocr_session.id))
            else:
                # OCR 실패 처리
                error_msg = result.get('error', '알 수 없는 오류')
                logger.error("OCR 실패: session_id=%s, %s", ocr_session.id, error_msg)

                ocr_session.status = 'failed'
                ocr_session.error_message = error_msg
                _commit_or_flash('OCR 상태를 저장하지 못했습니다.', 'Could not persist the OCR status.')
                
                flash('OCR 처리에 실패했습니다.' if session.get('language') == 'ko' else 'OCR processing failed.', 'danger')
                return redirect(url_for('ocr_scan'))
        
        except Exception as e:
            logger.exception("OCR 처리 오류: session_id=%s, file=%s", ocr_session.id, filepath)

            db.session.rollback()
            ocr_session.status = 'failed'
            ocr_session.error_message = str(e)
            _commit_or_flash('OCR 상태를 저장하지 못했습니다.', 'Could not persist the OCR status.')
            
            flash('OCR 처리 중 오류가 발생했습니다.' if session.get('language') == 'ko' else 'OCR processing error.', 'danger')
            return redirect(url_for('ocr_scan'))
    
    except Exception as e:
        db.session.rollback()
        logger.exception("OCR 파일 업로드 오류")

        flash(f'파일 업로드 중 오류가 발생했습니다: {e}' if session.get('language') == 'ko'
              else f'File upload error: {e}', 'danger')
        return redirect(url_for('ocr_scan'))
    
    # ✅ 이 부분은 절대 실행되지 않지만, 안전을 위해 추가
    return redirect(url_for('ocr_scan'))

@app.route('/ocr/verify/<int:session_id>')
@login_required
def ocr_verify(session_id):
    """OCR 데이터 검증 화면"""
    ocr_session = OCRSession.query.get_or_404(session_id)
    
    denied = _deny_if_not_owner(ocr_session, 'dashboard')
    if denied:
        return denied

    # 데이터 확인
    if not ocr_session.extracted_data:
        flash('추출된 데이터가 없습니다.' if session.get('language') == 'ko' else 'No extracted data.', 'danger')
        return redirect(url_for('ocr_scan'))
    
    data = ocr_session.extracted_data.get('data', [])
    image_url = url_for('uploaded_file', filename=ocr_session.filename)
    
    return render_template('ocr_verify.html', 
                         data=data, 
                         session_id=session_id,
                         image_url=image_url,
                         enumerate=enumerate)

@app.route('/ocr/save/<int:session_id>', methods=['POST'])
@login_required
def ocr_save(session_id):
    """OCR 데이터 저장"""
    try:
        ocr_session = OCRSession.query.get_or_404(session_id)
        
        denied = _deny_if_not_owner(ocr_session, 'dashboard')
        if denied:
            return denied
        
        # 폼 데이터
        dataset_name = request.form.get('dataset_name')
        description = request.form.get('description', '')
        data_json = request.form.get('data')
        
        if not dataset_name or not data_json:
            flash('필수 항목을 입력해주세요.' if session.get('language') == 'ko' else 'Please fill in required fields.', 'danger')
            return redirect(url_for('ocr_verify', session_id=session_id))
        
        # JSON 파싱
        try:
            data_dict = json.loads(data_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("OCR 저장 요청의 data 필드가 유효한 JSON이 아닙니다: session_id=%s", session_id,
                           exc_info=True)
            flash('전송된 데이터 형식이 올바르지 않습니다.' if session.get('language') == 'ko'
                  else 'The submitted data format is invalid.', 'danger')
            return redirect(url_for('ocr_verify', session_id=session_id))

        headers = data_dict.get('headers', [])
        rows = data_dict.get('rows', [])
        
        # DataFrame 생성
        df = pd.DataFrame(rows, columns=headers)
        
        # Excel 파일로 저장
        excel_filename = f"ocr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(dataset_name)}.xlsx"
        excel_filepath = os.path.join(upload_folder(), excel_filename)
        df.to_excel(excel_filepath, index=False)

        create_dataset_with_records(
            df,
            name=dataset_name,
            description=description,
            filename=excel_filename,
            file_path=excel_filepath,
            user_id=current_user.id,
            is_ocr=True
        )
        db.session.commit()
        
        flash('데이터가 성공적으로 저장되었습니다!' if session.get('language') == 'ko' else 'Data saved successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    except Exception:
        db.session.rollback()
        logger.exception("OCR 데이터 저장 오류: session_id=%s", session_id)
        flash('데이터 저장 중 오류가 발생했습니다.' if session.get('language') == 'ko' else 'Error saving data.', 'danger')
        return redirect(url_for('ocr_verify', session_id=session_id))

# 업로드된 파일 제공
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """업로드된 파일 제공 (본인이 업로드한 파일만)"""
    if filename != secure_filename(filename):
        return redirect(url_for('dashboard'))

    expected_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    owns_dataset = Dataset.query.filter_by(user_id=current_user.id, file_path=expected_path).first()
    owns_ocr_file = OCRSession.query.filter_by(user_id=current_user.id, filename=filename).first()

    if not owns_dataset and not owns_ocr_file:
        flash(get_message('접근 권한이 없습니다.', 'Access denied.'), 'danger')
        return redirect(url_for('dashboard'))

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


####################

####################
# ================================
# templates
# ================================
# 템플릿 데이터 디렉토리 설정
TEMPLATE_FOLDER = os.path.join(os.path.dirname(__file__), 'templates_data')
os.makedirs(TEMPLATE_FOLDER, exist_ok=True)

# 템플릿 정보
TEMPLATES = {
    'crop_yield': {
        'name_ko': '곡물 생산량 분석',
        'name_en': 'Crop Yield Analysis',
        'filename': 'crop_yield_template.csv',
        'description_ko': '작물 종류, 토양, 기후 데이터 기반 생산량 예측',
        'description_en': 'Crop type, soil, climate data for yield prediction',
        'icon': '🌾',
        'target_column': 'Crop_Yield'
    },
    'sales_data': {
        'name_ko': '판매 데이터 분석',
        'name_en': 'Sales Data Analysis',
        'filename': 'sales_data_template.csv',
        'description_ko': '제품별, 지역별 판매 실적 분석',
        'description_en': 'Sales performance by product and region',
        'icon': '🛒',
        'target_column': 'Total_Sales'
    },
    'customer_data': {
        'name_ko': '고객 분석',
        'name_en': 'Customer Analysis',
        'filename': 'customer_data_template.csv',
        'description_ko': '고객 세그멘테이션 및 구매 패턴 분석',
        'description_en': 'Customer segmentation and purchase patterns',
        'icon': '👥',
        'target_column': 'Total_Purchases'
    },
    'marketing_campaign': {
        'name_ko': '마케팅 캠페인 분석',
        'name_en': 'Marketing Campaign Analysis',
        'filename': 'marketing_campaign_template.csv',
        'description_ko': '캠페인 성과 및 ROI 분석',
        'description_en': 'Campaign performance and ROI analysis',
        'icon': '📢',
        'target_column': 'Revenue'
    }
}


@app.route('/template_analysis')
@login_required
def template_analysis():
    """템플릿 분석 페이지"""
    return render_template('template_analysis.html')


@app.route('/download_template/<template_name>')
@login_required
def download_template(template_name):
    """템플릿 다운로드"""
    try:
        if template_name not in TEMPLATES:
            flash('존재하지 않는 템플릿입니다.' if session.get('language') == 'ko' else 'Template not found.', 'danger')
            return redirect(url_for('template_analysis'))
        
        template_info = TEMPLATES[template_name]
        filename = template_info['filename']
        
        return send_from_directory(
            TEMPLATE_FOLDER,
            filename,
            as_attachment=True,
            download_name=filename
        )
    
    except HTTPException:
        raise
    except Exception:
        logger.exception("템플릿 다운로드 오류: %s", template_name)
        flash('템플릿 다운로드 중 오류가 발생했습니다.' if session.get('language') == 'ko' else 'Error downloading template.', 'danger')
        return redirect(url_for('template_analysis'))


@app.route('/template_analyze', methods=['POST'])
@login_required
def template_analyze():
    """템플릿 파일 업로드 및 분석"""
    try:
        # 파일 확인
        if 'file' not in request.files:
            flash('파일이 없습니다.' if session.get('language') == 'ko' else 'No file uploaded.', 'danger')
            return redirect(url_for('template_analysis'))
        
        file = request.files['file']
        template_type = request.form.get('template_type')
        
        if not file.filename:
            flash('파일이 선택되지 않았습니다.' if session.get('language') == 'ko' else 'No file selected.', 'danger')
            return redirect(url_for('template_analysis'))
        
        if not template_type or template_type not in TEMPLATES:
            flash('템플릿 유형을 선택하세요.' if session.get('language') == 'ko' else 'Select template type.', 'danger')
            return redirect(url_for('template_analysis'))
        
        # 파일 확장자 확인
        if not file.filename.endswith('.csv'):
            flash('CSV 파일만 업로드 가능합니다.' if session.get('language') == 'ko' else 'Only CSV files allowed.', 'danger')
            return redirect(url_for('template_analysis'))
        
        try:
            file_path, _ = save_upload(file, 'template', template_type)
        except OSError:
            logger.exception("템플릿 파일 저장 실패: %s", file.filename)
            flash_msg('save_failed', 'danger')
            return redirect(url_for('template_analysis'))

        unique_filename = os.path.basename(file_path)

        print(f"✅ 템플릿 파일 저장: {file_path}")
        
        # 데이터 읽기
        df = pd.read_csv(file_path)
        
        print(f"✅ 데이터 로드: {df.shape}")
        print(f"컬럼: {df.columns.tolist()}")
        
        auto_analysis = request.form.get('auto_analysis') == 'true'
        save_dataset  = request.form.get('save_dataset') == 'true'

        # 자동 분석이면 무조건 DB 저장 (분석 페이지에 dataset_id 필요)
        if auto_analysis or save_dataset:
            template_info = TEMPLATES[template_type]
            dataset_name = f"{template_info['name_ko']} - {datetime.now().strftime('%Y-%m-%d')}"

            dataset = create_dataset_with_records(
                df,
                name=dataset_name,
                description=f"Template: {template_type}",
                filename=unique_filename,
                file_path=file_path,
                user_id=current_user.id,
                sanitize=True,
                is_template=True
            )
            db.session.commit()
            print(f"✅ 데이터셋 저장: {dataset.id} ({len(df)}행)")

        if auto_analysis:
            return redirect(url_for('view_template_analysis', dataset_id=dataset.id))
        else:
            flash('파일이 성공적으로 업로드되었습니다.' if session.get('language') == 'ko' else 'File uploaded successfully.', 'success')
            return redirect(url_for('template_analysis'))
    
    except HTTPException:
        raise
    except Exception:
        db.session.rollback()
        logger.exception("템플릿 분석 오류: template_type=%s", request.form.get('template_type'))

        flash('오류가 발생했습니다.' if session.get('language') == 'ko' else 'An error occurred.', 'danger')
        return redirect(url_for('template_analysis'))

ANALYTICS_TABS = ('timeseries', 'outlier', 'correlation', 'rfm', 'pareto', 'cohort', 'abtest')
# 세그먼트 분석은 주기 선택 폭이 좁다 (일/주 코호트는 표가 과도하게 커짐)
COHORT_FREQS = ('W', 'M', 'Q', 'Y')
RFM_SEGMENT_LABELS = {
    'champions': ('충성 우수 고객', 'Champions'),
    'loyal': ('단골 고객', 'Loyal'),
    'potential': ('신규·성장 가능', 'Potential'),
    'at_risk': ('이탈 위험', 'At risk'),
    'hibernating': ('휴면', 'Hibernating'),
    'others': ('기타', 'Others'),
}


def _int_arg(name, default, minimum, maximum):
    """쿼리 파라미터를 범위 안의 정수로 읽는다 (잘못된 값은 기본값)."""
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _float_arg(name, default, minimum, maximum):
    try:
        value = float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _column_arg(name, columns, default=None):
    """데이터셋에 실제로 존재하는 컬럼만 허용한다."""
    value = request.args.get(name)
    if value in columns:
        return value
    return default


def _table_rows(frame, extra_columns=None):
    """NaN 은 Jinja 의 none 검사에 걸리지 않아 그대로 출력되므로 None 으로 바꾼다."""
    cleaned = frame.astype(object).where(pd.notna(frame), None)
    rows = cleaned.to_dict('records')
    if extra_columns:
        for row, (index, _) in zip(rows, cleaned.iterrows()):
            row.update(extra_columns(index))
    return rows


def _figures_json(figures):
    return {key: fig.to_json() for key, fig in (figures or {}).items() if fig is not None}


def _timeseries_insights(result, value_col):
    """시계열 결과를 사람이 읽는 문장으로 요약한다."""
    stats = result['stats']
    lines = []
    change = stats['last_change_pct']
    if change is not None:
        lines.append(get_message(
            f'최근 기간 {value_col}은(는) 직전 기간 대비 <strong>{change:+.1f}%</strong> 변화했습니다.',
            f'{value_col} changed <strong>{change:+.1f}%</strong> versus the previous period.'
        ))
    if stats['last_yoy_pct'] is not None:
        lines.append(get_message(
            f'전년 동기 대비 증감률은 <strong>{stats["last_yoy_pct"]:+.1f}%</strong>입니다.',
            f'Year-over-year change is <strong>{stats["last_yoy_pct"]:+.1f}%</strong>.'
        ))
    direction = get_message('상승', 'upward') if stats['slope'] > 0 else get_message('하락', 'downward')
    lines.append(get_message(
        f'전체 추세는 <strong>{direction}</strong> 방향입니다 (기간당 {stats["slope"]:,.1f}).',
        f'The overall trend is <strong>{direction}</strong> ({stats["slope"]:,.1f} per period).'
    ))
    if stats['forecast_next'] is not None:
        lines.append(get_message(
            f'다음 기간 예측값은 <strong>{stats["forecast_next"]:,.0f}</strong>입니다 (선형 추세 + 계절 성분).',
            f'Next-period forecast is <strong>{stats["forecast_next"]:,.0f}</strong> (linear trend + seasonality).'
        ))
    return lines


def _outlier_insights(result, value_col):
    lower, upper = result['bounds']
    method_label = 'IQR' if result['method'] == 'iqr' else 'Z-score'
    lines = [get_message(
        f'{method_label} 기준(±{result["threshold"]})으로 {result["total"]}건 중 '
        f'<strong>{result["count"]}건({result["pct"]:.1f}%)</strong>이 이상치로 탐지되었습니다.',
        f'{result["count"]} of {result["total"]} rows '
        f'(<strong>{result["pct"]:.1f}%</strong>) are outliers by {method_label} (±{result["threshold"]}).'
    )]
    lines.append(get_message(
        f'정상 범위는 {lower:,.1f} ~ {upper:,.1f} 입니다.',
        f'The normal range for {value_col} is {lower:,.1f} to {upper:,.1f}.'
    ))
    return lines


def _correlation_insights(result):
    lines = []
    for first, second, value in result['pairs'][:3]:
        strength = (get_message('강한', 'strong') if abs(value) >= 0.7
                    else get_message('보통', 'moderate') if abs(value) >= 0.4
                    else get_message('약한', 'weak'))
        direction = get_message('양', 'positive') if value > 0 else get_message('음', 'negative')
        lines.append(get_message(
            f'{first} ↔ {second}: <strong>r = {value:.2f}</strong> ({strength} {direction}의 상관)',
            f'{first} ↔ {second}: <strong>r = {value:.2f}</strong> ({strength} {direction} correlation)'
        ))
    return lines


def _contribution_insights(result):
    coefficients = result['coefficients']
    lines = [get_message(
        f'선형 모델 설명력 R² = <strong>{result["r_squared"]:.2f}</strong> (표본 {result["sample_size"]}건)',
        f'Model fit R² = <strong>{result["r_squared"]:.2f}</strong> (n = {result["sample_size"]})'
    )]
    for name, value in coefficients.head(3).items():
        effect = get_message('증가', 'increases') if value > 0 else get_message('감소', 'decreases')
        lines.append(get_message(
            f'{name}이(가) 1 표준편차 오르면 {result["target"]}은(는) '
            f'{abs(value):.2f} 표준편차 {effect}합니다.',
            f'A 1 SD increase in {name} {effect} {result["target"]} by {abs(value):.2f} SD.'
        ))
    return lines


def _segment_label(key):
    labels = RFM_SEGMENT_LABELS.get(key, (key, key))
    return get_message(labels[0], labels[1])


def _rfm_insights(result, value_col):
    stats = result['stats']
    segments = result['segments']
    top = stats['top_segment']
    lines = [get_message(
        f'고객 {stats["customers"]}명을 RFM 점수로 분류했습니다 (기준일 {stats["reference_date"]}).',
        f'Scored {stats["customers"]} customers with RFM (reference date {stats["reference_date"]}).'
    ), get_message(
        f'가장 큰 세그먼트는 <strong>{_segment_label(top)}</strong>({segments[top]}명)입니다.',
        f'The largest segment is <strong>{_segment_label(top)}</strong> ({segments[top]} customers).'
    ), get_message(
        f'평균 최근성 {stats["avg_recency"]:.0f}일, 평균 거래 {stats["avg_frequency"]:.1f}회, '
        f'평균 {value_col} {stats["avg_monetary"]:,.0f}.',
        f'Average recency {stats["avg_recency"]:.0f} days, {stats["avg_frequency"]:.1f} transactions, '
        f'{value_col} {stats["avg_monetary"]:,.0f}.'
    )]
    if segments.get('at_risk'):
        lines.append(get_message(
            f'<strong>이탈 위험</strong> 세그먼트 {segments["at_risk"]}명은 재구매 유도 대상입니다.',
            f'<strong>At risk</strong> segment has {segments["at_risk"]} customers to win back.'
        ))
    return lines


def _pareto_insights(result, category_col, value_col):
    stats = result['stats']
    return [get_message(
        f'{category_col} {stats["categories"]}개 중 상위 20%가 {value_col}의 '
        f'<strong>{stats["top20_pct"]:.1f}%</strong>를 차지합니다.',
        f'The top 20% of {stats["categories"]} {category_col} values account for '
        f'<strong>{stats["top20_pct"]:.1f}%</strong> of {value_col}.'
    ), get_message(
        f'최대 기여 항목은 <strong>{stats["top_category"]}</strong>'
        f'({stats["top_category_pct"]:.1f}%)입니다.',
        f'The biggest contributor is <strong>{stats["top_category"]}</strong> '
        f'({stats["top_category_pct"]:.1f}%).'
    ), get_message(
        f'ABC 등급: A {stats["a_count"]}개(누적 80% 이내), B {stats["b_count"]}개(95% 이내), '
        f'C {stats["c_count"]}개.',
        f'ABC classes: A {stats["a_count"]} (within 80% of value), B {stats["b_count"]} (within 95%), '
        f'C {stats["c_count"]}.'
    )]


def _cohort_insights(result):
    stats = result['stats']
    lines = [get_message(
        f'고객 {stats["customers"]}명을 첫 거래 시점 기준 {stats["cohorts"]}개 코호트로 나눴습니다.',
        f'Split {stats["customers"]} customers into {stats["cohorts"]} cohorts by first activity.'
    )]
    if stats['avg_repeat_pct'] is not None:
        lines.append(get_message(
            f'다음 기간 재방문율 평균은 <strong>{stats["avg_repeat_pct"]:.1f}%</strong>입니다.',
            f'Average next-period retention is <strong>{stats["avg_repeat_pct"]:.1f}%</strong>.'
        ))
        lines.append(get_message(
            f'가장 좋은 코호트는 <strong>{stats["best_cohort"]}</strong>'
            f'({stats["best_cohort_pct"]:.1f}%)입니다.',
            f'The best cohort is <strong>{stats["best_cohort"]}</strong> '
            f'({stats["best_cohort_pct"]:.1f}%).'
        ))
    return lines


def _format_p_value(value):
    """p-value 를 반올림으로 0 이 되지 않게 표기한다."""
    if value < 0.0001:
        return f'{value:.2e}'
    return f'{value:.4f}'


def _abtest_insights(result, value_col):
    first, second = result['groups']
    value_a, value_b = result['values']
    metric_label = (get_message('전환율', 'conversion rate') if result['metric'] == 'conversion'
                    else get_message(f'평균 {value_col}', f'mean {value_col}'))
    lines = [get_message(
        f'{first} {value_a:,.3f} vs {second} {value_b:,.3f} ({metric_label}, '
        f'표본 {result["sizes"][0]}/{result["sizes"][1]}건)',
        f'{first} {value_a:,.3f} vs {second} {value_b:,.3f} ({metric_label}, '
        f'n = {result["sizes"][0]}/{result["sizes"][1]})'
    )]
    if result['lift_pct'] is not None:
        lines.append(get_message(
            f'차이는 {result["difference"]:+,.3f} (<strong>{result["lift_pct"]:+.1f}%</strong>)입니다.',
            f'The difference is {result["difference"]:+,.3f} '
            f'(<strong>{result["lift_pct"]:+.1f}%</strong>).'
        ))
    verdict = (get_message('통계적으로 유의합니다', 'statistically significant')
               if result['significant']
               else get_message('통계적으로 유의하지 않습니다', 'not statistically significant'))
    lines.append(get_message(
        f'{result["test"]} 결과 p = <strong>{_format_p_value(result["p_value"])}</strong> → '
        f'유의수준 {result["alpha"]:.2f}에서 {verdict}.',
        f'{result["test"]}: p = <strong>{_format_p_value(result["p_value"])}</strong> → {verdict} '
        f'at α = {result["alpha"]:.2f}.'
    ))
    low, high = result['confidence_interval']
    lines.append(get_message(
        f'차이의 95% 신뢰구간은 {low:,.3f} ~ {high:,.3f} 입니다.',
        f'The 95% confidence interval for the difference is {low:,.3f} to {high:,.3f}.'
    ))
    return lines


def _analytics_options(df):
    return {
        'numeric': numeric_columns(df),
        'datetime': datetime_columns(df),
        'categorical': categorical_columns(df),
        'freqs': list(FREQ_RULES),
        'cohort_freqs': list(COHORT_FREQS),
        'aggs': list(AGG_FUNCS),
        'metrics': list(AB_METRICS),
    }


def _analytics_params(columns, options):
    """쿼리 파라미터를 검증된 분석 설정으로 변환한다 (컬럼은 화이트리스트)."""
    tab = request.args.get('tab', 'timeseries')
    if tab not in ANALYTICS_TABS:
        tab = 'timeseries'

    first_numeric = options['numeric'][0] if options['numeric'] else None
    first_date = options['datetime'][0] if options['datetime'] else None
    first_category = options['categorical'][0] if options['categorical'] else None
    return {
        'tab': tab,
        'date_col': _column_arg('date_col', columns, first_date),
        'value_col': _column_arg('value_col', columns, first_numeric),
        'freq': request.args.get('freq') if request.args.get('freq') in FREQ_RULES else 'M',
        'agg': request.args.get('agg') if request.args.get('agg') in AGG_FUNCS else 'sum',
        'window': _int_arg('window', 3, 2, 24),
        'horizon': _int_arg('horizon', 3, 0, 24),
        'method': 'zscore' if request.args.get('method') == 'zscore' else 'iqr',
        'threshold': _float_arg('threshold', 1.5, 0.5, 6.0),
        'group_col': _column_arg('group_col', columns),
        'target_col': _column_arg('target_col', columns, first_numeric),
        'customer_col': _column_arg('customer_col', columns, first_category),
        'category_col': _column_arg('category_col', columns, first_category),
        'cohort_freq': (request.args.get('cohort_freq')
                        if request.args.get('cohort_freq') in COHORT_FREQS else 'M'),
        'periods': _int_arg('periods', 12, 3, 24),
        'metric': 'conversion' if request.args.get('metric') == 'conversion' else 'mean',
    }


def _run_analytics(df, columns, params):
    """선택한 탭의 분석을 실행해 차트/인사이트/표/지표를 돌려준다."""
    tab = params['tab']
    charts, insights, tables, stats = {}, [], {}, {}
    if tab == 'timeseries' and params['date_col'] and params['value_col']:
        result = timeseries_analysis(
            df, params['date_col'], params['value_col'],
            freq=params['freq'], agg=params['agg'],
            window=params['window'], horizon=params['horizon']
        )
        if result:
            charts = _figures_json(result['figures'])
            stats = result['stats']
            insights = _timeseries_insights(result, params['value_col'])
            table = result['table'].tail(24).round(2)
            tables['timeseries'] = {
                'columns': ['period', 'value', 'moving_avg', 'change_pct', 'yoy_pct'],
                'rows': _table_rows(
                    table,
                    lambda index: {'period': index.strftime('%Y-%m-%d')}
                ),
            }

    elif tab == 'outlier' and params['value_col']:
        result = outlier_analysis(
            df, params['value_col'], method=params['method'],
            threshold=params['threshold'], group_col=params['group_col']
        )
        if result:
            charts = _figures_json(result['figures'])
            stats = {key: result[key] for key in ('count', 'total', 'pct')}
            insights = _outlier_insights(result, params['value_col'])
            tables['outlier'] = {
                'columns': columns,
                'rows': _table_rows(result['rows'][columns].round(2)),
            }

    elif tab == 'correlation':
        result = correlation_analysis(df)
        if result:
            charts = _figures_json(result['figures'])
            insights = _correlation_insights(result)
            tables['correlation'] = {
                'columns': ['x', 'y', 'r'],
                'rows': [{'x': first, 'y': second, 'r': round(value, 3)}
                         for first, second, value in result['pairs']],
            }
            stats = {'sample_size': result['sample_size']}
        if params['target_col']:
            contribution = contribution_analysis(df, params['target_col'])
            if contribution:
                charts.update(_figures_json(contribution['figures']))
                insights += _contribution_insights(contribution)

    elif tab == 'rfm' and params['customer_col'] and params['date_col'] and params['value_col']:
        result = rfm_analysis(df, params['customer_col'], params['date_col'],
                              params['value_col'])
        if result:
            charts = _figures_json(result['figures'])
            stats = result['stats']
            insights = _rfm_insights(result, params['value_col'])
            table = result['table']
            table['segment'] = [_segment_label(value) for value in table['segment']]
            tables['rfm'] = {
                'columns': ['customer', 'recency', 'frequency', 'monetary',
                            'r_score', 'f_score', 'm_score', 'segment'],
                'rows': _table_rows(table.round(2)),
            }

    elif tab == 'pareto' and params['category_col'] and params['value_col']:
        result = pareto_analysis(df, params['category_col'], params['value_col'])
        if result:
            charts = _figures_json(result['figures'])
            stats = result['stats']
            insights = _pareto_insights(result, params['category_col'], params['value_col'])
            tables['pareto'] = {
                'columns': ['category', 'value', 'share_pct', 'cumulative_pct', 'abc'],
                'rows': _table_rows(result['table'].round(2)),
            }

    elif tab == 'cohort' and params['customer_col'] and params['date_col']:
        result = cohort_analysis(df, params['customer_col'], params['date_col'],
                                 freq=params['cohort_freq'], max_periods=params['periods'])
        if result:
            charts = _figures_json(result['figures'])
            stats = result['stats']
            insights = _cohort_insights(result)
            tables['cohort'] = {
                'columns': result['table'].columns.tolist(),
                'rows': _table_rows(result['table']),
            }

    elif tab == 'abtest' and params['group_col'] and params['value_col']:
        result = ab_test_analysis(df, params['group_col'], params['value_col'],
                                  metric=params['metric'])
        if result:
            charts = _figures_json(result['figures'])
            # 지표 카드는 읽힌 우선 — p 는 문자열로, 유의성은 문구로 넣는다
            stats = {key: result[key] for key in ('test', 'difference', 'lift_pct')}
            stats['p_value'] = _format_p_value(result['p_value'])
            stats['significant'] = (get_message('유의함', 'Significant')
                                    if result['significant']
                                    else get_message('유의하지 않음', 'Not significant'))
            stats['sample_sizes'] = ' / '.join(str(size) for size in result['sizes'])
            insights = _abtest_insights(result, params['value_col'])
            tables['abtest'] = {
                'columns': ['group', 'size', 'value'],
                'rows': [{'group': group, 'size': size, 'value': round(value, 4)}
                         for group, size, value
                         in zip(result['groups'], result['sizes'], result['values'])],
            }
    return charts, insights, tables, stats


@app.route('/analytics/<int:dataset_id>')
@login_required
def advanced_analytics(dataset_id):
    """고급 분석 (시계열/이상치/상관·기여도/RFM/파레토/코호트/A·B 검정)"""
    dataset = Dataset.query.get_or_404(dataset_id)

    denied = _deny_if_not_owner(dataset, 'dashboard')
    if denied:
        return denied

    fix_dataset_meta(dataset)
    df = load_dataset_dataframe(dataset_id)
    if df.empty:
        flash_msg('no_data', 'warning')
        return redirect(url_for('view_dataset', dataset_id=dataset_id))

    columns = df.columns.tolist()
    options = _analytics_options(df)
    params = _analytics_params(columns, options)

    charts, insights, tables, stats = {}, [], {}, {}
    try:
        charts, insights, tables, stats = _run_analytics(df, columns, params)
    except Exception:
        logger.exception("고급 분석 실패: dataset=%s tab=%s", dataset_id, params['tab'])
        flash(get_message('분석을 완료하지 못했습니다. 선택한 컬럼을 확인해주세요.',
                          'Could not complete the analysis. Please check the selected columns.'), 'warning')

    if not charts and not insights:
        flash(get_message('선택한 컬럼으로 분석할 데이터가 충분하지 않습니다.',
                          'Not enough data to analyze with the selected columns.'), 'info')

    return render_template('analytics.html', dataset=dataset, columns=columns,
                           options=options, params=params, charts=charts,
                           insights=insights, tables=tables, stats=stats)


def _insight_text(lines):
    """리포트용 — 인사이트 문구에서 서식 태그를 제거한다."""
    return [re.sub(r'</?(strong|em|br)>', '', line) for line in lines]


@app.route('/analytics/<int:dataset_id>/export')
@login_required
def export_analytics(dataset_id):
    """현재 분석 탭의 지표·인사이트·표를 Excel 로 내린다."""
    dataset = Dataset.query.get_or_404(dataset_id)

    denied = _deny_if_not_owner(dataset, 'dashboard')
    if denied:
        return denied

    fix_dataset_meta(dataset)
    df = load_dataset_dataframe(dataset_id)
    if df.empty:
        flash_msg('no_data', 'warning')
        return redirect(url_for('view_dataset', dataset_id=dataset_id))

    columns = df.columns.tolist()
    params = _analytics_params(columns, _analytics_options(df))
    try:
        _, insights, tables, stats = _run_analytics(df, columns, params)
    except Exception:
        logger.exception("분석 내보내기 실패: dataset=%s tab=%s", dataset_id, params['tab'])
        flash(get_message('리포트를 만들지 못했습니다. 설정을 확인해주세요.',
                          'Could not build the report. Please check the settings.'), 'warning')
        return redirect(url_for('advanced_analytics', dataset_id=dataset_id, **params))

    if not insights and not tables:
        flash(get_message('내보낼 분석 결과가 없습니다.', 'There is no analysis result to export.'),
              'info')
        return redirect(url_for('advanced_analytics', dataset_id=dataset_id, **params))

    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        summary = [
            ('dataset', dataset.name),
            ('analysis', params['tab']),
            ('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M')),
        ]
        summary += [(key, value) for key, value in stats.items()]
        summary += [(f'insight_{index + 1}', line)
                    for index, line in enumerate(_insight_text(insights))]
        pd.DataFrame(summary, columns=['item', 'value']).to_excel(
            writer, sheet_name='summary', index=False)
        for name, table in tables.items():
            pd.DataFrame(table['rows'], columns=table['columns']).to_excel(
                writer, sheet_name=name[:31], index=False)
    stream.seek(0)

    filename = f"analytics_{dataset_id}_{params['tab']}_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        stream, as_attachment=True, download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/analytics/<int:dataset_id>/report')
@login_required
def analytics_report(dataset_id):
    """인쇄/PDF 저장용 리포트 화면 (차트 포함)."""
    dataset = Dataset.query.get_or_404(dataset_id)

    denied = _deny_if_not_owner(dataset, 'dashboard')
    if denied:
        return denied

    fix_dataset_meta(dataset)
    df = load_dataset_dataframe(dataset_id)
    if df.empty:
        flash_msg('no_data', 'warning')
        return redirect(url_for('view_dataset', dataset_id=dataset_id))

    columns = df.columns.tolist()
    params = _analytics_params(columns, _analytics_options(df))
    charts, insights, tables, stats = {}, [], {}, {}
    try:
        charts, insights, tables, stats = _run_analytics(df, columns, params)
    except Exception:
        logger.exception("리포트 생성 실패: dataset=%s tab=%s", dataset_id, params['tab'])
        flash(get_message('리포트를 만들지 못했습니다. 설정을 확인해주세요.',
                          'Could not build the report. Please check the settings.'), 'warning')

    return render_template('analytics_report.html', dataset=dataset, params=params,
                           charts=charts, insights=insights, tables=tables, stats=stats,
                           generated_at=datetime.now().strftime('%Y-%m-%d %H:%M'))


####################
@app.route('/manual')
def manual():
    """사용자 매뉴얼 (한국어/영문)"""
    return render_template('manual.html')

@app.route('/examples')
@login_required
def examples():
    """분석 예시 목록 페이지"""
    return render_template('examples.html')

@app.route('/example/<template_type>')
@login_required
def example_view(template_type):
    """템플릿별 예시 분석 페이지 (샘플 CSV 직접 렌더링)"""
    if template_type not in TEMPLATES:
        flash('잘못된 템플릿 유형입니다.' if session.get('language') == 'ko' else 'Invalid template type.', 'danger')
        return redirect(url_for('examples'))

    sample_file = os.path.join(TEMPLATE_FOLDER, TEMPLATES[template_type]['filename'])
    if not os.path.exists(sample_file):
        flash('샘플 파일을 찾을 수 없습니다.' if session.get('language') == 'ko' else 'Sample file not found.', 'danger')
        return redirect(url_for('examples'))

    df = pd.read_csv(sample_file)
    failures = []
    charts  = generate_template_charts(df, failures)
    metrics = calculate_metrics(df, failures)

    from types import SimpleNamespace
    from datetime import datetime as dt
    fake_dataset = SimpleNamespace(
        name=TEMPLATES[template_type]['name_ko'] + ' 예시',
        uploaded_at=dt.now(),
        row_count=len(df)
    )

    insights = generate_insights(df, failures)
    _flash_analysis_failures(failures)

    return render_template('template_result.html',
                           dataset=fake_dataset,
                           charts=charts,
                           metrics=metrics,
                           insights=insights,
                           data=df.head(100).to_dict('records'),
                           columns=df.columns.tolist())


@app.route('/crop_example')
@login_required
def crop_example():
    """작물 생산량 분석 예시 화면"""
    import os
    import plotly.io as pio
    # 샘플 데이터 파일 경로
    sample_file = os.path.join(TEMPLATE_FOLDER, 'crop_yield_template.csv')
    
    # 파일이 없으면 생성
    if not os.path.exists(sample_file):
        # 샘플 데이터 생성
        sample_data = """Crop_Type,Soil_Type,Climate,Rainfall_mm,Temperature_C,Fertilizer_kg,Irrigation_hours,Crop_Yield_kg
                            Wheat,Loamy,Temperate,450,18,120,40,4200
                            Rice,Clay,Tropical,1200,28,150,80,5800
                            Corn,Sandy,Subtropical,600,24,100,50,4800
                            Barley,Loamy,Temperate,400,16,110,35,3900
                            Soybean,Clay,Temperate,500,22,90,45,3200
                            Wheat,Clay,Temperate,480,19,125,42,4350
                            Rice,Loamy,Tropical,1150,27,145,75,5600
                            Corn,Clay,Subtropical,620,25,105,52,4950
                            Barley,Sandy,Temperate,420,17,115,38,4050
                            Soybean,Loamy,Temperate,520,21,95,48,3350"""
        
        with open(sample_file, 'w', encoding='utf-8') as f:
            f.write(sample_data)
    
    # 데이터 로드
    df = pd.read_csv(sample_file)
    
    # 주요 지표 계산
    metrics = {
        'avg_yield': int(df['Crop_Yield_kg'].mean()),
        'max_yield': int(df['Crop_Yield_kg'].max()),
        'crop_count': df['Crop_Type'].nunique(),
        'total_records': len(df)
    }
    
    # 차트 생성
    charts = {}
    
    # 1. 작물별 평균 생산량 (바 차트)
    crop_avg = df.groupby('Crop_Type')['Crop_Yield_kg'].mean().reset_index()
    crop_avg = crop_avg.sort_values('Crop_Yield_kg', ascending=False)
    fig1 = px.bar(crop_avg, x='Crop_Type', y='Crop_Yield_kg',
                  title='Average Yield by Crop Type',
                  labels={'Crop_Type': 'Crop Type', 'Crop_Yield_kg': 'Yield (kg)'},
                  color='Crop_Yield_kg',
                  color_continuous_scale='Greens')
    fig1.update_layout(height=400, showlegend=False)
    charts['crop_avg_yield'] = fig1.to_json()
    
    # 2. 토양 타입별 생산량 (바 차트)
    soil_avg = df.groupby('Soil_Type')['Crop_Yield_kg'].mean().reset_index()
    fig2 = px.bar(soil_avg, x='Soil_Type', y='Crop_Yield_kg',
                  title='Average Yield by Soil Type',
                  labels={'Soil_Type': 'Soil Type', 'Crop_Yield_kg': 'Yield (kg)'},
                  color='Crop_Yield_kg',
                  color_continuous_scale='brwnyl')
    fig2.update_layout(height=400, showlegend=False)
    charts['soil_yield'] = fig2.to_json()
    
    # 3. 강수량 vs 생산량 (산점도)
    fig3 = px.scatter(df, x='Rainfall_mm', y='Crop_Yield_kg',
                      color='Crop_Type',
                      title='Rainfall vs Crop Yield',
                      labels={'Rainfall_mm': 'Rainfall (mm)', 'Crop_Yield_kg': 'Yield (kg)'},
                      trendline="ols",
                      size='Crop_Yield_kg',
                      size_max=15)
    fig3.update_layout(height=400)
    charts['rainfall_yield'] = fig3.to_json()
    
    # 4. 기온 vs 생산량 (산점도)
    fig4 = px.scatter(df, x='Temperature_C', y='Crop_Yield_kg',
                      color='Crop_Type',
                      title='Temperature vs Crop Yield',
                      labels={'Temperature_C': 'Temperature (°C)', 'Crop_Yield_kg': 'Yield (kg)'},
                      trendline="ols",
                      size='Crop_Yield_kg',
                      size_max=15)
    fig4.update_layout(height=400)
    charts['temp_yield'] = fig4.to_json()
    
    # 5. 작물 종류 분포 (파이 차트)
    crop_counts = df['Crop_Type'].value_counts().reset_index()
    crop_counts.columns = ['Crop_Type', 'count']
    fig5 = px.pie(crop_counts, names='Crop_Type', values='count',
                  title='Crop Type Distribution',
                  hole=0.3)
    fig5.update_layout(height=400)
    charts['crop_distribution'] = fig5.to_json()
    
    # 6. 비료 사용량 vs 생산량 (산점도)
    fig6 = px.scatter(df, x='Fertilizer_kg', y='Crop_Yield_kg',
                      color='Crop_Type',
                      title='Fertilizer Usage vs Crop Yield',
                      labels={'Fertilizer_kg': 'Fertilizer (kg)', 'Crop_Yield_kg': 'Yield (kg)'},
                      trendline="ols",
                      size='Crop_Yield_kg',
                      size_max=15)
    fig6.update_layout(height=400)
    charts['fertilizer_yield'] = fig6.to_json()
    
    # 샘플 데이터 (처음 10행)
    sample_data = df.head(10).to_dict('records')
    
    return render_template('crop_example.html',
                         metrics=metrics,
                         charts=charts,
                         sample_data=sample_data)


###############################33

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', '5000'))
    app.run(debug=debug, host=host, port=port)
