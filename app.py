from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config
import pandas as pd
import json
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from models import db, User, Dataset, DataRecord, DataView, OCRSession
from src.analysis_utils import (
    correlation, gain_pct, group_agg, group_ratio, ratio_pct, top_share
)
from src.chart_utils import (
    QUALITATIVE_COLORS, add_month_column, base_layout, distribution_by_group,
    group_sum, grouped_bar, horizontal_bar, line_trend, pie_chart, resolve_column,
    resolve_columns, scatter_by_group, simple_bar, to_numeric_column,
    try_parse_date_column, value_counts_frame
)
from src.dataset_utils import (
    access_denied, create_dataset_from_dataframe, dataframe_rows, fix_dataset_meta,
    is_owner, load_dataset_dataframe, read_dataframe, save_upload, upload_folder
)
from src.i18n import flash_msg, get_message, msg



app = Flask(__name__)
app.config.from_object(Config)

# 데이터베이스 초기화
db.init_app(app)

# 로그인 매니저 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 언어 설정
@app.before_request
def before_request():
    if 'language' not in session:
        session['language'] = app.config['DEFAULT_LANGUAGE']

@app.route('/set_language/<language>')
def set_language(language):
    if language in app.config['LANGUAGES']:
        session['language'] = language
    return redirect(request.referrer or url_for('index'))

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
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        company = request.form.get('company', '')  # 회사명 추가 (선택사항)
        
        if User.query.filter_by(email=email).first():
            flash_msg('email_taken', 'danger')
            return redirect(url_for('register'))
        
        user = User(email=email, name=name, company=company)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash_msg('registered', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# 로그인
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash_msg('logged_in', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash_msg('invalid_credentials', 'danger')
    
    return render_template('login.html')

# 로그아웃
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash_msg('logged_out', 'success')
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
            _, filepath, _ = save_upload(file, [current_user.id])

            try:
                df = read_dataframe(filepath)
                dataset = create_dataset_from_dataframe(
                    df,
                    name=name,
                    description=description,
                    filename=file.filename,
                    file_path=filepath
                )
                db.session.commit()
                flash_msg('data_uploaded', 'success')
                return redirect(url_for('view_dataset', dataset_id=dataset.id))

            except Exception as e:
                db.session.rollback()
                flash_msg('file_process_error', 'danger', error=str(e))
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(url_for('upload'))
        else:
            flash_msg('invalid_file_format', 'danger')

    return render_template('upload.html')


# 데이터셋 보기
@app.route('/dataset/<int:dataset_id>')
@login_required
def view_dataset(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)

    if not is_owner(dataset):
        return access_denied('dashboard')

    fix_dataset_meta(dataset)
    records = DataRecord.query.filter_by(dataset_id=dataset_id).limit(100).all()
    data = [record.data for record in records]

    return render_template('view_dataset.html', dataset=dataset, data=data, columns=dataset.columns or [])

# 데이터 시각화
@app.route('/visualize/<int:dataset_id>')
@login_required
def visualize(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)

    if not is_owner(dataset):
        return access_denied('dashboard')

    fix_dataset_meta(dataset)
    columns = dataset.columns if dataset.columns is not None else []
    return render_template('visualize.html', dataset=dataset, columns=columns)

def _apply_axis_titles(fig, x_column, y_column, is_x_date, is_y_date):
    """축 제목 설정 (날짜 축이면 type='date') — 라인/바/산점도 공통"""
    y_kwargs = dict(title_text=y_column, autorange=True)
    if is_y_date:
        y_kwargs['type'] = 'date'
    fig.update_yaxes(**y_kwargs)

    x_kwargs = dict(title_text=x_column)
    if is_x_date:
        x_kwargs['type'] = 'date'
    fig.update_xaxes(**x_kwargs)


def _plain_trace_values(trace, key, series=None):
    """trace 값을 순수 JSON 리스트로 변환 (Plotly 바이너리 인코딩 방지)

    날짜 컬럼은 타임스탬프 대신 ISO 문자열로 직렬화한다.
    """
    value = trace[key]
    if value is None:
        return

    is_binary_encoded = isinstance(value, dict) and 'dtype' in value
    if not is_binary_encoded and not hasattr(value, 'tolist'):
        if not isinstance(value, list):
            trace[key] = list(value)
        return

    if series is not None and series.dtype == 'datetime64[ns]':
        trace[key] = series.dt.strftime('%Y-%m-%d').tolist()
    elif is_binary_encoded:
        trace[key] = series.tolist()
    else:
        trace[key] = value.tolist()


# 차트 생성 API
@app.route('/api/generate_chart', methods=['POST'])
@login_required
def generate_chart():
    try:
        data = request.json
        dataset_id = data.get('dataset_id')
        chart_type = data.get('chart_type')
        x_column = data.get('x_column')
        y_column = data.get('y_column')
        
        print(f"\n=== 차트 생성 요청 / Chart Generation Request ===")
        print(f"Dataset ID: {dataset_id}")
        print(f"Chart Type: {chart_type}")
        print(f"X Column: {x_column}")
        print(f"Y Column: {y_column}")
        
        dataset = Dataset.query.get_or_404(dataset_id)
        
        if not is_owner(dataset):
            return jsonify({'error': msg('access_denied')}), 403
        
        # 데이터 레코드 가져오기
        records = DataRecord.query.filter_by(dataset_id=dataset_id).all()
        if not records:
            return jsonify({'error': msg('no_data')}), 400
        
        print(f"총 레코드 수 / Total records: {len(records)}")
        
        df = load_dataset_dataframe(dataset_id)
        print(f"DataFrame shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        
        # 컬럼 존재 확인
        if x_column not in df.columns:
            return jsonify({'error': msg('column_not_found', value=x_column)}), 400
        if y_column and y_column not in df.columns:
            return jsonify({'error': msg('column_not_found', value=y_column)}), 400
        
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
                    print(f"Y축 원본 타입: {df[y_column].dtype}")
                    try:
                        is_y_date = try_parse_date_column(df, y_column)
                        if not is_y_date:
                            raise ValueError("Not a date column")
                        print(f"✅ Y축을 날짜로 변환함")
                    except Exception:
                        # 날짜 변환 실패 -> 숫자 변환 시도
                        to_numeric_column(df, y_column)
                        print(f"Y 컬럼을 숫자로 변환함")
                    print(f"Y 컬럼 변환 후 dtype: {df[y_column].dtype}")
                    print(f"Y 컬럼 변환 후 샘플: {df[y_column].head(3).tolist()}")

                # X축 처리
                if chart_type == 'histogram':
                    # 히스토그램은 X축도 숫자여야 함
                    to_numeric_column(df, x_column)
                else:
                    # 라인/바/산점도의 경우 X축을 날짜로 변환 시도
                    try:
                        is_x_date = try_parse_date_column(df, x_column)
                        if is_x_date:
                            print(f"✅ X축을 날짜로 변환함")
                    except Exception:
                        pass

            elif chart_type == 'pie':
                # 파이 차트는 values를 숫자로 변환, names는 문자열로 유지
                if y_column:
                    to_numeric_column(df, y_column)
                    print(f"파이 차트 Y 변환 후: {df[y_column].dtype}")
                # X축(names)은 문자열로 유지 (카테고리)
                df[x_column] = df[x_column].astype(str)
                print(f"파이 차트 X를 문자열로 유지: {df[x_column].dtype}")
                print(f"X 값 샘플: {df[x_column].head(3).tolist()}")

        except Exception as conv_error:
            print(f"⚠️  데이터 변환 경고 / Data conversion warning: {conv_error}")
        
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
            return jsonify({'error': msg('no_valid_data')}), 400
        
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
            except Exception as sort_error:
                print(f"정렬 실패: {sort_error}")
        
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
                _apply_axis_titles(fig, x_column, y_column, is_x_date, is_y_date)
            
            elif chart_type == 'bar':
                print(f"\n바 차트 생성 중...")
                fig = px.bar(plot_df, x=x_column, y=y_column, 
                           title=get_message(f'{x_column}별 {y_column}', f'{y_column} by {x_column}'))
                _apply_axis_titles(fig, x_column, y_column, is_x_date, is_y_date)
            
            elif chart_type == 'scatter':
                print(f"\n산점도 생성 중...")
                fig = px.scatter(plot_df, x=x_column, y=y_column, 
                               title=get_message(f'{y_column} vs {x_column}', f'{y_column} vs {x_column}'))
                _apply_axis_titles(fig, x_column, y_column, is_x_date, is_y_date)
            
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
                    pie_data = value_counts_frame(plot_df, x_column)
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
                return jsonify({'error': msg('unsupported_chart')}), 400
            
            # 차트 레이아웃 개선
            fig.update_layout(
                font=dict(size=12),
                hovermode='closest',
                showlegend=True,
                height=500,
                margin=dict(l=70, r=50, t=80, b=70),
                xaxis=dict(fixedrange=False),
                yaxis=dict(fixedrange=False)
            )
            
            # 생성된 차트의 데이터 확인
            print(f"\n생성된 차트 정보:")
            print(f"X축 데이터 포인트 수: {len(fig.data[0].x) if hasattr(fig.data[0], 'x') else 'N/A'}")
            if hasattr(fig.data[0], 'y') and fig.data[0].y is not None:
                print(f"Y축 데이터 포인트 수: {len(fig.data[0].y)}")
                y_values = list(fig.data[0].y)
                print(f"Y축 값 범위: {min(y_values)} ~ {max(y_values)}")

            
            print("✅ 차트 생성 성공 / Chart created successfully\n")
            
            # PlotlyJSONEncoder를 사용하면 바이너리 인코딩됨
            # 대신 to_plotly_json()을 사용하거나 수동으로 변환
            
            # 방법 1: fig를 dict로 변환 후 x, y, labels, values를 명시적으로 리스트로 변환
            fig_dict = fig.to_dict()
            
            # 모든 trace의 x, y, labels, values 데이터를 Python list로 강제 변환
            y_series = df[y_column] if y_column else None
            for trace in fig_dict.get('data', []):
                if 'x' in trace:
                    _plain_trace_values(trace, 'x', df[x_column])
                if 'y' in trace:
                    _plain_trace_values(trace, 'y', y_series)
                if 'labels' in trace:
                    _plain_trace_values(trace, 'labels')
                if 'values' in trace:
                    _plain_trace_values(trace, 'values')

            # 일반 json.dumps 사용 (PlotlyJSONEncoder 없이)
            graphJSON = json.dumps(fig_dict)
            
            # JSON 확인 (디버깅)
            print(f"\n📊 생성된 JSON 정보:")
            print(f"JSON 길이: {len(graphJSON)} 바이트")
            
            # X 데이터 부분 확인
            if '"x":' in graphJSON:
                x_start = graphJSON.find('"x":')
                x_sample = graphJSON[x_start:x_start+300]
                print(f"X 데이터 샘플: {x_sample[:150]}...")
                if any(ts in x_sample for ts in ['1704', '1705', '1706']):
                    print("⚠️ 경고: X축이 여전히 타임스탬프 숫자입니다!")
                elif '"2024-' in x_sample or '"2023-' in x_sample:
                    print("✅ 확인: X축이 날짜 문자열 형식입니다!")
            
            # Y 데이터 부분 확인
            if '"y":' in graphJSON:
                y_start = graphJSON.find('"y":')
                y_sample = graphJSON[y_start:y_start+200]
                print(f"Y 데이터 샘플: {y_sample}")
                if '"dtype"' in y_sample or '"bdata"' in y_sample:
                    print("❌ 경고: Y축이 여전히 바이너리 인코딩입니다!")
                else:
                    print("✅ 확인: Y축이 순수 JSON 배열 형식입니다!")
            
            return jsonify({'chart': graphJSON})
        
        except Exception as plot_error:
            error_msg = str(plot_error)
            print(f"❌ 차트 생성 오류 / Chart creation error: {error_msg}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': msg('chart_failed', error=error_msg)}), 400
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 전체 오류 / General error: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': msg('error_occurred', error=error_msg)}), 400

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
        _, filepath, timestamp = save_upload(file, [current_user.id, 'template'])

        try:
            df = read_dataframe(filepath)
            dataset = create_dataset_from_dataframe(
                df,
                name=f"Template Analysis {timestamp}",
                description="Template-based automated analysis",
                filename=file.filename,
                file_path=filepath,
                is_template=True
            )
            db.session.commit()
            flash_msg('template_uploaded', 'success')
            return redirect(url_for('view_template_analysis', dataset_id=dataset.id))

        except Exception as e:
            db.session.rollback()
            flash_msg('file_process_error', 'danger', error=str(e))
            if os.path.exists(filepath):
                os.remove(filepath)
            return redirect(url_for('template_dashboard'))
    else:
        flash_msg('invalid_file_format', 'danger')
        return redirect(url_for('template_dashboard'))

# 템플릿 기반 자동 분석 뷰
@app.route('/template/analysis/<int:dataset_id>')
@login_required
def view_template_analysis(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if not is_owner(dataset):
        return access_denied('template_dashboard')
    
    df = load_dataset_dataframe(dataset_id)
    
    # 자동으로 차트 생성
    charts   = generate_template_charts(df)
    metrics  = calculate_metrics(df)
    insights = generate_insights(df)

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
def generate_template_charts(df):
    charts = {}
    common_layout = base_layout()

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

    except Exception as e:
        import traceback
        print(f"차트 생성 오류: {e}")
        traceback.print_exc()

    return charts


def _charts_sales(df, charts, layout):
    col_date, col_revenue, col_region, col_product, col_category, col_quantity, col_cost = resolve_columns(
        df, '날짜', '매출액', '지역', '제품', '카테고리', '판매량', '비용'
    )

    month_col = add_month_column(df, col_date) if col_date else None

    # 1. 월별 매출 vs 비용 비교 (그룹 바 or 라인)
    if col_date and col_revenue:
        if col_cost:
            monthly = group_sum(df, month_col, [col_revenue, col_cost])
            fig = grouped_bar(monthly[month_col], [
                ('매출', monthly[col_revenue], '#0d6efd'),
                ('비용', monthly[col_cost], '#dc3545'),
            ], title='월별 매출 vs 비용', x_title='월', layout=layout)
        else:
            monthly = group_sum(df, month_col, col_revenue)
            fig = line_trend(monthly, month_col, col_revenue, title='월별 매출 추이',
                             color='#0d6efd', layout=layout)
        charts['daily_sales'] = fig.to_json()

    # 2. 지역별 매출 (수평 바, 내림차순)
    if col_region and col_revenue:
        data = group_sum(df, col_region, col_revenue, sort_by=col_revenue)
        fig = horizontal_bar(data, col_revenue, col_region, title='지역별 매출 (내림차순)',
                             layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 제품별 판매 비율 (도넛 차트)
    if col_product and col_revenue:
        data = group_sum(df, col_product, col_revenue, sort_by=col_revenue, ascending=False)
        fig = pie_chart(data, col_product, col_revenue, title='제품별 매출 비중',
                        hole=0.4, layout=layout)
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
        fig = scatter_by_group(df, col_quantity, col_revenue, color_col=color_arg,
                               title='판매량 vs 매출액',
                               x_label='판매량', y_label='매출액', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 제품별 이익률 (수평 바)
    if col_product and col_revenue and col_cost:
        data = group_ratio(df, col_product, col_revenue, col_cost, '이익률(%)',
                           mode='margin')
        fig = horizontal_bar(data, '이익률(%)', col_product, title='제품별 이익률(%)',
                             color_scale='RdYlGn', layout=layout)
        charts['daily_quantity'] = fig.to_json()
    elif col_date and col_quantity:
        x_col = month_col if month_col else col_date
        daily = group_sum(df, x_col, col_quantity)
        fig = line_trend(daily, x_col, col_quantity, title='월별 판매량 추이',
                         color='#198754', layout=layout)
        charts['daily_quantity'] = fig.to_json()


def _charts_crop(df, charts, layout):
    col_crop, col_yield, col_climate, col_soil, col_rain, col_temp, col_fert, col_irr = resolve_columns(
        df, '작물', '수확량', '기후', '토양', '강수량', '온도', '비료', '관개'
    )

    # 1. 작물별 수확량 분포 (박스 플롯)
    if col_crop and col_yield:
        fig = distribution_by_group(df, col_yield, col_crop, kind='box',
                                    title='작물 유형별 수확량 분포',
                                    y_title='수확량 (kg)', showlegend=True, layout=layout)
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
        fig = distribution_by_group(df, col_yield, col_climate, kind='box',
                                    title='기후별 수확량 분포',
                                    y_title='수확량 (kg)', showlegend=True, layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 작물별 데이터 구성 비율 (도넛)
    if col_crop:
        counts = value_counts_frame(df, col_crop)
        fig = pie_chart(counts, col_crop, 'count', title='작물 유형 구성 비율',
                        hole=0.4, layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 토양 유형별 수확량 분포 (바이올린)
    if col_soil and col_yield:
        fig = distribution_by_group(df, col_yield, col_soil, kind='violin',
                                    title='토양 유형별 수확량 분포',
                                    y_title='수확량 (kg)', showlegend=True, layout=layout)
        charts['category_sales'] = fig.to_json()

    # 5. 강수량 vs 수확량 (작물별 색상, 비료량 = 마커 크기)
    if col_rain and col_yield:
        fig = scatter_by_group(df, col_rain, col_yield, color_col=col_crop,
                               size_col=col_fert, size_max=18,
                               title='강수량 vs 수확량 (마커 크기 = 비료량)',
                               x_label='강수량 (mm)', y_label='수확량 (kg)', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 온도 vs 수확량 (작물별 색상)
    if col_temp and col_yield:
        fig = scatter_by_group(df, col_temp, col_yield, color_col=col_crop,
                               title='기온 vs 수확량',
                               x_label='기온 (°C)', y_label='수확량 (kg)', layout=layout)
        fig.update_traces(marker=dict(size=9, opacity=0.7))
        charts['daily_quantity'] = fig.to_json()


def _charts_marketing(df, charts, layout):
    col_channel, col_revenue, col_budget, col_clicks, col_conv, col_impr, col_date, col_camp = resolve_columns(
        df, '채널', '매출액', '예산', '클릭', '전환', '노출', '날짜', '캠페인'
    )

    month_col = add_month_column(df, col_date) if col_date else None

    # 1. 월별 매출 + 예산 추이 (그룹 바)
    if month_col and col_revenue and col_budget:
        monthly = group_sum(df, month_col, [col_revenue, col_budget])
        fig = grouped_bar(monthly[month_col], [
            ('매출', monthly[col_revenue], '#0d6efd'),
            ('예산', monthly[col_budget], '#adb5bd'),
        ], title='월별 매출 vs 예산', x_title='월', layout=layout)
        charts['daily_sales'] = fig.to_json()
    elif month_col and col_revenue:
        monthly = group_sum(df, month_col, col_revenue)
        fig = line_trend(monthly, month_col, col_revenue, title='월별 매출 추이', layout=layout)
        charts['daily_sales'] = fig.to_json()

    # 2. 채널별 ROI (수평 바 — ROI% = (매출-예산)/예산*100)
    if col_channel and col_revenue and col_budget:
        agg = group_ratio(df, col_channel, col_revenue, col_budget, 'ROI(%)', mode='gain')
        fig = horizontal_bar(agg, 'ROI(%)', col_channel, title='채널별 ROI (%)',
                             color_scale='RdYlGn', text_col='ROI(%)',
                             text_template='%{text:.1f}%', layout=layout)
        charts['region_sales'] = fig.to_json()
    elif col_channel and col_revenue:
        data = group_sum(df, col_channel, col_revenue, sort_by=col_revenue)
        fig = horizontal_bar(data, col_revenue, col_channel, title='채널별 총 매출',
                             layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 채널별 캠페인 예산 비중 (도넛)
    if col_channel and col_budget:
        data = group_sum(df, col_channel, col_budget)
        fig = pie_chart(data, col_channel, col_budget, title='채널별 예산 배분',
                        hole=0.4, layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 채널별 전환율 (전환/클릭 × 100, 수평 바)
    if col_channel and col_conv and col_clicks:
        agg = group_ratio(df, col_channel, col_conv, col_clicks, '전환율(%)', decimals=2)
        fig = horizontal_bar(agg, '전환율(%)', col_channel, title='채널별 전환율 (%)',
                             color_scale='Teal', text_col='전환율(%)',
                             text_template='%{text:.2f}%', layout=layout)
        charts['category_sales'] = fig.to_json()
    elif col_channel and col_conv:
        data = group_sum(df, col_channel, col_conv, sort_by=col_conv)
        fig = horizontal_bar(data, col_conv, col_channel, title='채널별 총 전환수',
                             color_scale='Teal', layout=layout)
        charts['category_sales'] = fig.to_json()

    # 5. 예산 vs 매출 버블 차트 (채널 색상, 노출수 = 크기)
    if col_budget and col_revenue:
        fig = scatter_by_group(df, col_budget, col_revenue, color_col=col_channel,
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
        fig = scatter_by_group(df, col_clicks, col_conv, color_col=col_channel,
                               title='클릭수 vs 전환수',
                               x_label='클릭수', y_label='전환수', layout=layout)
        charts['daily_quantity'] = fig.to_json()


def _charts_customer(df, charts, layout):
    col_seg, col_age, col_gender, col_income, col_purch, col_value = resolve_columns(
        df, '세그먼트', '나이', '성별', '소득', '구매횟수', '구매금액'
    )
    col_recency = 'Last_Purchase_Days' if 'Last_Purchase_Days' in df.columns else None

    # 1. 연령 × 세그먼트 분포 (히스토그램)
    if col_age:
        group_col = col_seg if col_seg else col_gender
        title = '고객 연령대 분포 (세그먼트별)' if group_col else '고객 연령 분포'
        fig = distribution_by_group(df, col_age, group_col, kind='histogram',
                                    title=title, x_title='나이', nbins=15,
                                    barmode='stack', layout=layout)
        charts['daily_sales'] = fig.to_json()

    # 2. 세그먼트별 총 구매금액 (수평 바, 내림차순)
    if col_seg and col_value:
        data = group_sum(df, col_seg, col_value, sort_by=col_value)
        fig = horizontal_bar(data, col_value, col_seg, title='세그먼트별 총 구매금액',
                             text_auto='.2s', layout=layout)
        charts['region_sales'] = fig.to_json()
    elif col_seg:
        counts = value_counts_frame(df, col_seg)
        fig = simple_bar(counts, col_seg, 'count', title='세그먼트별 고객 수', layout=layout)
        charts['region_sales'] = fig.to_json()

    # 3. 성별 구매금액 비중 (도넛)
    if col_gender and col_value:
        data = group_sum(df, col_gender, col_value)
        fig = pie_chart(data, col_gender, col_value, title='성별 구매금액 비중', hole=0.4,
                        layout=layout, color_discrete_sequence=px.colors.qualitative.Pastel)
        charts['product_distribution'] = fig.to_json()
    elif col_gender:
        counts = value_counts_frame(df, col_gender)
        fig = pie_chart(counts, col_gender, 'count', title='성별 비율', hole=0.4, layout=layout)
        charts['product_distribution'] = fig.to_json()

    # 4. 세그먼트별 구매금액 분포 (박스 플롯)
    if col_seg and col_value:
        fig = distribution_by_group(df, col_value, col_seg, kind='box',
                                    title='세그먼트별 구매금액 분포',
                                    y_title='평균 구매금액', showlegend=True, layout=layout)
        charts['category_sales'] = fig.to_json()

    # 5. 소득 vs 구매금액 (세그먼트 색상, 구매횟수 = 마커 크기)
    if col_income and col_value:
        color_arg = col_seg if col_seg else col_gender
        fig = scatter_by_group(df, col_income, col_value, color_col=color_arg,
                               size_col=col_purch, size_max=18,
                               title='소득 vs 구매금액 (마커 크기 = 구매횟수)',
                               x_label='소득', y_label='평균 구매금액', layout=layout)
        charts['quantity_revenue'] = fig.to_json()

    # 6. 구매 주기 분포 (히스토그램)
    if col_recency:
        fig = distribution_by_group(df, col_recency, col_seg, kind='histogram',
                                    title='마지막 구매 후 경과일 분포 (구매 주기)',
                                    x_title='경과일 (일)', nbins=20,
                                    barmode='stack', layout=layout)
        charts['daily_quantity'] = fig.to_json()
    elif col_age and col_purch:
        fig = scatter_by_group(df, col_age, col_purch,
                               color_col=col_seg if col_seg else None,
                               title='연령 vs 총 구매횟수',
                               x_label='나이', y_label='총 구매횟수', layout=layout)
        charts['daily_quantity'] = fig.to_json()


def _charts_generic(df, charts, layout):
    """알 수 없는 템플릿 — 숫자/범주형 컬럼으로 자동 차트 생성"""
    num_cols = df.select_dtypes(include='number').columns.tolist()
    cat_cols = df.select_dtypes(include='object').columns.tolist()

    if cat_cols and num_cols:
        data = group_sum(df, cat_cols[0], num_cols[0], sort_by=num_cols[0], ascending=False).head(15)
        fig = px.bar(data, x=cat_cols[0], y=num_cols[0], title=f'{cat_cols[0]}별 {num_cols[0]}')
        fig.update_layout(**layout)
        charts['region_sales'] = fig.to_json()

    if len(num_cols) >= 2:
        fig = px.scatter(df, x=num_cols[0], y=num_cols[1], title=f'{num_cols[0]} vs {num_cols[1]}')
        fig.update_layout(**layout)
        charts['quantity_revenue'] = fig.to_json()

    if cat_cols:
        counts = value_counts_frame(df, cat_cols[0], top=10)
        fig = pie_chart(counts, cat_cols[0], 'count', title=f'{cat_cols[0]} 분포', layout=layout)
        charts['product_distribution'] = fig.to_json()

# 주요 지표 계산 함수 (4개 템플릿 전체 지원)
def _sum_avg_metrics(metrics, df, column, total_key, avg_key, decimals=None):
    """합계/평균 지표 기록 (decimals=None → 정수 반올림)"""
    if not column:
        return
    metrics[total_key] = int(df[column].sum())
    mean = df[column].mean()
    metrics[avg_key] = int(mean) if decimals is None else round(mean, decimals)


def _profit_metrics(metrics, df, value_col, cost_col, mode='margin'):
    """수익 지표 기록 — mode='margin'은 이익률, 'gain'은 ROI"""
    if not (value_col and cost_col):
        return
    total, cost = df[value_col].sum(), df[cost_col].sum()
    metrics['total_profit'] = int(total - cost)
    metrics['profit_margin'] = round(
        gain_pct(total, cost) if mode == 'gain' else ratio_pct(total - cost, total), 1
    )


def calculate_metrics(df):
    metrics = {}
    try:
        ttype = _detect_template_type(df)
        metrics['total_records'] = len(df)

        if ttype == 'sales':
            col_revenue, col_quantity, col_cost, col_product = resolve_columns(
                df, '매출액', '판매량', '비용', '제품'
            )
            _sum_avg_metrics(metrics, df, col_revenue, 'total_revenue', 'avg_revenue')
            _sum_avg_metrics(metrics, df, col_quantity, 'total_quantity', 'avg_quantity', decimals=1)
            _profit_metrics(metrics, df, col_revenue, col_cost)
            if col_product:
                metrics['unique_products'] = df[col_product].nunique()

        elif ttype == 'crop':
            col_crop, col_yield, col_rain = resolve_columns(df, '작물', '수확량', '강수량')
            _sum_avg_metrics(metrics, df, col_yield, 'total_revenue', 'avg_revenue')
            _sum_avg_metrics(metrics, df, col_rain, 'total_quantity', 'avg_quantity', decimals=1)
            if col_crop:
                metrics['unique_products'] = df[col_crop].nunique()

        elif ttype == 'marketing':
            col_revenue, col_budget, col_conv, col_clicks = resolve_columns(
                df, '매출액', '예산', '전환', '클릭'
            )
            _sum_avg_metrics(metrics, df, col_revenue, 'total_revenue', 'avg_revenue')
            _profit_metrics(metrics, df, col_revenue, col_budget, mode='gain')
            _sum_avg_metrics(metrics, df, col_conv, 'total_quantity', 'avg_quantity', decimals=1)

        elif ttype == 'customer':
            col_purch, col_value, col_seg = resolve_columns(df, '구매횟수', '구매금액', '세그먼트')
            _sum_avg_metrics(metrics, df, col_value, 'total_revenue', 'avg_revenue')
            _sum_avg_metrics(metrics, df, col_purch, 'total_quantity', 'avg_quantity', decimals=1)
            if col_seg:
                metrics['unique_products'] = df[col_seg].nunique()

    except Exception as e:
        print(f"지표 계산 오류: {e}")

    return metrics

# ── 차트별 인사이트 자동 생성 ──────────────────────────────────────
# TODO: 추후 Claude API 연동으로 교체 예정
# 각 chart_key → 분석 텍스트 반환 (template_result.html에서 카드 하단에 표시)
def generate_insights(df):
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
    except Exception as e:
        print(f"인사이트 생성 오류: {e}")
    return insights


def _insights_sales(df):
    ins = {}
    col_date, col_revenue, col_region, col_product, col_category, col_quantity, col_cost = resolve_columns(
        df, '날짜', '매출액', '지역', '제품', '카테고리', '판매량', '비용'
    )

    if col_date and col_revenue:
        df2 = df.copy()
        month_col = add_month_column(df2, col_date)
        monthly = df2.groupby(month_col)[col_revenue].sum()
        growth = gain_pct(monthly.iloc[-1], monthly.iloc[0]) if len(monthly) > 1 else 0
        ins['daily_sales'] = (
            f"📈 최고 매출 월은 <strong>{monthly.idxmax()}</strong> "
            f"({int(monthly.max()):,}원), 최저는 <strong>{monthly.idxmin()}</strong> ({int(monthly.min()):,}원)입니다. "
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
        ins['category_sales'] = (
            f"📦 <strong>{by_cat.index[0]}</strong> 카테고리가 가장 높은 매출을 기록했습니다. "
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
        margins = group_ratio(df, col_product, col_revenue, col_cost, 'margin',
                              mode='margin', sort=False).set_index(col_product)['margin']
        best, worst = margins.idxmax(), margins.idxmin()
        ins['daily_quantity'] = (
            f"💰 이익률이 가장 높은 제품은 <strong>{best}</strong> ({margins[best]:.1f}%), "
            f"가장 낮은 제품은 <strong>{worst}</strong> ({margins[worst]:.1f}%)입니다. "
            f"저마진 제품의 원가 절감 또는 가격 재조정을 검토하세요."
        )
    return ins


def _insights_crop(df):
    ins = {}
    col_crop, col_yield, col_climate, col_soil, col_rain, col_temp, col_fert = resolve_columns(
        df, '작물', '수확량', '기후', '토양', '강수량', '온도', '비료'
    )

    if col_crop and col_yield:
        by_crop = group_agg(df, col_crop, col_yield, how='mean')
        ins['daily_sales'] = (
            f"🌾 <strong>{by_crop.index[0]}</strong>이 평균 {int(by_crop.iloc[0]):,}kg으로 가장 높은 수확량을 보입니다. "
            f"<strong>{by_crop.index[-1]}</strong>와의 차이는 {int(by_crop.iloc[0] - by_crop.iloc[-1]):,}kg이며, "
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
        ins['product_distribution'] = (
            f"📋 데이터셋에서 <strong>{counts.index[0]}</strong>이 전체의 {ratio_pct(counts.iloc[0], len(df)):.1f}%를 차지합니다. "
            f"균형 잡힌 비교 분석을 위해 각 작물별 데이터 수가 균등한지 확인하세요."
        )

    if col_soil and col_yield:
        by_soil = group_agg(df, col_soil, col_yield, how='median')
        ins['category_sales'] = (
            f"🌱 <strong>{by_soil.index[0]}</strong> 토양이 중앙값 기준으로 수확량이 가장 높습니다. "
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
    col_channel, col_revenue, col_budget, col_clicks, col_conv, col_impr = resolve_columns(
        df, '채널', '매출액', '예산', '클릭', '전환', '노출'
    )

    if col_revenue and col_budget:
        df2 = df.copy()
        to_numeric_column(df2, col_revenue)
        to_numeric_column(df2, col_budget)
        total_roi = gain_pct(df2[col_revenue].sum(), df2[col_budget].sum())

        col_date = resolve_column(df, '날짜')
        if col_date:
            month_col = add_month_column(df2, col_date)
            monthly_rev = df2.groupby(month_col)[col_revenue].sum()
            ins['daily_sales'] = (
                f"📅 전체 평균 ROI는 <strong>{total_roi:.1f}%</strong>입니다. "
                f"<strong>{monthly_rev.idxmax()}</strong>에 최대 매출 {int(monthly_rev.max()):,}원을 기록했습니다. "
                f"예산 대비 매출 막대가 큰 달의 캠페인 전략을 분석하세요."
            )

    if col_channel and col_revenue and col_budget:
        roi = group_ratio(df, col_channel, col_revenue, col_budget, 'roi',
                          mode='gain', sort=False).set_index(col_channel)['roi']
        best_ch, worst_ch = roi.idxmax(), roi.idxmin()
        ins['region_sales'] = (
            f"🎯 ROI 최고 채널: <strong>{best_ch}</strong> ({roi[best_ch]:.1f}%), "
            f"최저: <strong>{worst_ch}</strong> ({roi[worst_ch]:.1f}%). "
            f"{'음수 ROI 채널은 예산 조정 또는 캠페인 개선이 필요합니다.' if roi.min() < 0 else '모든 채널이 양의 ROI를 기록 중입니다.'}"
        )

    if col_channel and col_budget:
        top_ch, top_pct, _ = top_share(df, col_channel, col_budget)
        ins['product_distribution'] = (
            f"💸 예산의 <strong>{top_pct:.1f}%</strong>가 <strong>{top_ch}</strong> 채널에 집중되어 있습니다. "
            f"{'채널 다변화를 통해 리스크 분산을 고려하세요.' if top_pct > 40 else '채널별 예산 배분이 비교적 균등합니다.'}"
        )

    if col_channel and col_conv and col_clicks:
        cvr = group_ratio(df, col_channel, col_conv, col_clicks, 'cvr',
                          decimals=2, sort=False).set_index(col_channel)['cvr']
        best = cvr.idxmax()
        ins['category_sales'] = (
            f"✅ 전환율 1위 채널: <strong>{best}</strong> ({cvr[best]:.2f}%). "
            f"전체 평균 전환율은 {cvr.mean():.2f}%이며, "
            f"전환율이 낮은 채널은 랜딩 페이지 및 타겟팅 최적화를 검토하세요."
        )

    if col_budget and col_revenue:
        corr = correlation(df, col_budget, col_revenue)
        ins['quantity_revenue'] = (
            f"💰 예산-매출 상관계수: <strong>{corr:.2f}</strong>. "
            f"{'예산 투자가 매출로 효율적으로 전환되고 있습니다.' if corr > 0.7 else '예산 증가가 반드시 매출 증가로 이어지지 않습니다. 캠페인 품질을 점검하세요.'} "
            f"버블 크기(노출수)가 크지만 매출이 낮은 캠페인은 메시지 효과를 재검토하세요."
        )

    if col_channel and col_impr and col_clicks and col_conv:
        ctr = group_ratio(df, col_channel, col_clicks, col_impr, 'ctr',
                          decimals=2, sort=False).set_index(col_channel)['ctr']
        best_ctr = ctr.idxmax()
        ins['daily_quantity'] = (
            f"📣 퍼널 분석: 클릭률(CTR) 최고 채널은 <strong>{best_ctr}</strong> ({ctr[best_ctr]:.2f}%). "
            f"노출 대비 전환이 낮은 채널은 클릭 후 경험(UX, 오퍼) 개선이 필요합니다. "
            f"퍼널 각 단계의 이탈률을 분석해 병목 구간을 파악하세요."
        )
    return ins


def _insights_customer(df):
    ins = {}
    col_seg, col_age, col_gender, col_income, col_purch, col_value = resolve_columns(
        df, '세그먼트', '나이', '성별', '소득', '구매횟수', '구매금액'
    )
    col_recency = 'Last_Purchase_Days' if 'Last_Purchase_Days' in df.columns else None

    if col_age:
        mode_range = pd.cut(df[col_age], bins=[0, 20, 30, 40, 50, 60, 100]).value_counts().idxmax()
        ins['daily_sales'] = (
            f"👤 평균 고객 연령: <strong>{df[col_age].mean():.1f}세</strong>, "
            f"가장 많은 연령대: <strong>{mode_range}</strong>. "
            f"핵심 연령대에 맞는 마케팅 메시지와 채널 전략을 수립하세요."
        )

    if col_seg and col_value:
        top, top_pct, _ = top_share(df, col_seg, col_value)
        ins['region_sales'] = (
            f"💼 <strong>{top}</strong> 세그먼트가 총 구매금액의 <strong>{top_pct:.1f}%</strong>를 차지합니다. "
            f"고가치 세그먼트 유지에 집중하고, 저가치 세그먼트의 업셀링 기회를 모색하세요."
        )

    if col_gender and col_value:
        dominant, pct, _ = top_share(df, col_gender, col_value)
        ins['product_distribution'] = (
            f"⚖️ <strong>{dominant}</strong> 고객이 전체 구매금액의 <strong>{pct:.1f}%</strong>를 차지합니다. "
            f"{'성별 구매 격차가 크므로 비중이 낮은 성별 대상 프로모션을 검토하세요.' if pct > 60 else '성별 구매금액 비중이 비교적 균등합니다.'}"
        )

    if col_seg and col_value:
        by_seg = df.groupby(col_seg)[col_value]
        cv = (by_seg.std() / by_seg.mean()).sort_values(ascending=False)
        ins['category_sales'] = (
            f"📊 <strong>{cv.index[0]}</strong> 세그먼트 내 구매금액 편차가 가장 큽니다 (CV: {cv.iloc[0]:.2f}). "
            f"박스플롯에서 이상치(outlier)가 많은 세그먼트는 VIP 고객과 일반 고객이 혼재되어 있습니다. "
            f"세분화된 개인화 마케팅이 효과적입니다."
        )

    if col_income and col_value:
        corr = correlation(df, col_income, col_value)
        ins['quantity_revenue'] = (
            f"💳 소득-구매금액 상관계수: <strong>{corr:.2f}</strong>. "
            f"{'소득이 높을수록 구매금액도 높아 프리미엄 상품 전략이 유효합니다.' if corr > 0.5 else '소득과 구매금액의 상관이 낮습니다. 가격 감도보다 다른 요인(선호도, 브랜드)이 중요합니다.'} "
            f"마커 크기(구매횟수)가 클수록 충성 고객임을 나타냅니다."
        )

    if col_recency:
        churned_pct = ratio_pct((df[col_recency] > 90).sum(), len(df))
        ins['daily_quantity'] = (
            f"⏰ 평균 마지막 구매 후 경과일: <strong>{df[col_recency].mean():.1f}일</strong>. "
            f"90일 이상 미구매 고객 비율: <strong>{churned_pct:.1f}%</strong>. "
            f"{'이탈 위험 고객 비중이 높습니다. 재활성화 캠페인을 즉시 실행하세요.' if churned_pct > 30 else '고객 구매 주기가 양호합니다. 재구매 유도 타이밍을 최적화하세요.'}"
        )
    elif col_age and col_purch:
        corr = correlation(df, col_age, col_purch)
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
    
    if not is_owner(dataset):
        return access_denied('dashboard')
    
    if os.path.exists(dataset.file_path):
        os.remove(dataset.file_path)
    
    db.session.delete(dataset)
    db.session.commit()
    
    flash_msg('dataset_deleted', 'success')
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
            flash_msg('no_file_uploaded', 'danger')
            return redirect(url_for('ocr_scan'))
        
        file = request.files['file']
        
        if file.filename == '':
            flash_msg('no_file_selected', 'danger')
            return redirect(url_for('ocr_scan'))
        
        # 허용된 확장자 확인
        allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}
        if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            flash_msg('invalid_ocr_format', 'danger')
            return redirect(url_for('ocr_scan'))
        
        # 파일 저장
        unique_filename, filepath, _ = save_upload(file, ['ocr'])
        
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
                
                # 데이터를 리스트로 변환 (NaN → None 변환으로 JSON 직렬화 오류 방지)
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
                print(f"❌ OCR 실패: {error_msg}")
                
                ocr_session.status = 'failed'
                ocr_session.error_message = error_msg
                db.session.commit()
                
                flash_msg('ocr_failed', 'danger', error=error_msg)
                return redirect(url_for('ocr_scan'))
        
        except Exception as e:
            print(f"❌ OCR 처리 오류: {e}")
            import traceback
            traceback.print_exc()
            
            ocr_session.status = 'failed'
            ocr_session.error_message = str(e)
            db.session.commit()
            
            flash_msg('ocr_error', 'danger', error=str(e))
            return redirect(url_for('ocr_scan'))
    
    except Exception as e:
        print(f"❌ 파일 업로드 오류: {e}")
        import traceback
        traceback.print_exc()
        
        flash_msg('upload_error', 'danger')
        return redirect(url_for('ocr_scan'))
    
    # ✅ 이 부분은 절대 실행되지 않지만, 안전을 위해 추가
    return redirect(url_for('ocr_scan'))

@app.route('/ocr/verify/<int:session_id>')
@login_required
def ocr_verify(session_id):
    """OCR 데이터 검증 화면"""
    ocr_session = OCRSession.query.get_or_404(session_id)
    
    # 권한 확인
    if not is_owner(ocr_session):
        return access_denied()
    
    # 데이터 확인
    if not ocr_session.extracted_data:
        flash_msg('no_extracted_data', 'danger')
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
        
        # 권한 확인
        if not is_owner(ocr_session):
            return access_denied()
        
        # 폼 데이터
        dataset_name = request.form.get('dataset_name')
        description = request.form.get('description', '')
        data_json = request.form.get('data')
        
        if not dataset_name or not data_json:
            flash_msg('required_fields', 'danger')
            return redirect(url_for('ocr_verify', session_id=session_id))
        
        # JSON 파싱
        data_dict = json.loads(data_json)
        headers = data_dict.get('headers', [])
        rows = data_dict.get('rows', [])
        
        # DataFrame 생성
        df = pd.DataFrame(rows, columns=headers)
        
        # Excel 파일로 저장
        excel_filename = f"ocr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(dataset_name)}.xlsx"
        excel_filepath = os.path.join(upload_folder(), excel_filename)
        df.to_excel(excel_filepath, index=False)
        
        # 데이터셋 생성
        create_dataset_from_dataframe(
            df,
            name=dataset_name,
            description=description,
            filename=excel_filename,
            file_path=excel_filepath,
            is_ocr=True
        )
        db.session.commit()
        
        flash_msg('data_saved', 'success')
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        db.session.rollback()
        print(f"데이터 저장 오류: {e}")
        flash_msg('save_error', 'danger', error=str(e))
        return redirect(url_for('ocr_verify', session_id=session_id))

# 업로드된 파일 제공
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """업로드된 파일 제공"""
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
            flash_msg('template_not_found', 'danger')
            return redirect(url_for('template_analysis'))
        
        template_info = TEMPLATES[template_name]
        filename = template_info['filename']
        
        return send_from_directory(
            TEMPLATE_FOLDER,
            filename,
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        print(f"템플릿 다운로드 오류: {str(e)}")
        flash_msg('template_download_error', 'danger')
        return redirect(url_for('template_analysis'))


@app.route('/template_analyze', methods=['POST'])
@login_required
def template_analyze():
    """템플릿 파일 업로드 및 분석"""
    try:
        # 파일 확인
        if 'file' not in request.files:
            flash_msg('no_file_uploaded', 'danger')
            return redirect(url_for('template_analysis'))
        
        file = request.files['file']
        template_type = request.form.get('template_type')
        
        if not file.filename:
            flash_msg('no_file_selected', 'danger')
            return redirect(url_for('template_analysis'))
        
        if not template_type or template_type not in TEMPLATES:
            flash_msg('template_type_required', 'danger')
            return redirect(url_for('template_analysis'))
        
        # 파일 확장자 확인
        if not file.filename.endswith('.csv'):
            flash_msg('csv_only', 'danger')
            return redirect(url_for('template_analysis'))
        
        # 파일 저장
        unique_filename, file_path, _ = save_upload(file, ['template', template_type])

        print(f"✅ 템플릿 파일 저장: {file_path}")

        df = read_dataframe(file_path)
        
        print(f"✅ 데이터 로드: {df.shape}")
        print(f"컬럼: {df.columns.tolist()}")
        
        auto_analysis = request.form.get('auto_analysis') == 'true'
        save_dataset  = request.form.get('save_dataset') == 'true'

        # 자동 분석이면 무조건 DB 저장 (분석 페이지에 dataset_id 필요)
        if auto_analysis or save_dataset:
            template_info = TEMPLATES[template_type]
            dataset_name = f"{template_info['name_ko']} - {datetime.now().strftime('%Y-%m-%d')}"

            dataset = create_dataset_from_dataframe(
                df,
                name=dataset_name,
                description=f"Template: {template_type}",
                filename=unique_filename,
                file_path=file_path,
                sanitize=True,
                is_template=True
            )
            db.session.commit()
            print(f"✅ 데이터셋 저장: {dataset.id} ({len(df)}행)")

        if auto_analysis:
            return redirect(url_for('view_template_analysis', dataset_id=dataset.id))
        else:
            flash_msg('file_uploaded', 'success')
            return redirect(url_for('template_analysis'))
    
    except Exception as e:
        print(f"❌ 템플릿 분석 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        
        flash_msg('generic_error', 'danger', error=str(e))
        return redirect(url_for('template_analysis'))

####################
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
        flash_msg('invalid_template_type', 'danger')
        return redirect(url_for('examples'))

    sample_file = os.path.join(TEMPLATE_FOLDER, TEMPLATES[template_type]['filename'])
    if not os.path.exists(sample_file):
        flash_msg('sample_not_found', 'danger')
        return redirect(url_for('examples'))

    df = pd.read_csv(sample_file)
    charts  = generate_template_charts(df)
    metrics = calculate_metrics(df)

    from types import SimpleNamespace
    from datetime import datetime as dt
    fake_dataset = SimpleNamespace(
        name=TEMPLATES[template_type]['name_ko'] + ' 예시',
        uploaded_at=dt.now(),
        row_count=len(df)
    )

    insights = generate_insights(df)

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
    app.run(debug=True, host='0.0.0.0', port=5000)
