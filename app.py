from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config
import pandas as pd
import json
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objs as go
from models import db, User, Dataset, DataRecord, DataView, OCRSession



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

# 다국어 메시지 함수
def get_message(ko_msg, en_msg):
    return ko_msg if session.get('language') == 'ko' else en_msg

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
            flash(get_message('이미 등록된 이메일입니다.', 'Email already registered.'), 'danger')
            return redirect(url_for('register'))
        
        user = User(email=email, name=name, company=company)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash(get_message('회원가입이 완료되었습니다!', 'Registration successful!'), 'success')
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
            flash(get_message('로그인 되었습니다.', 'Successfully logged in.'), 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
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
            flash(get_message('파일이 선택되지 않았습니다.', 'No file selected.'), 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if file.filename == '':
            flash(get_message('파일이 선택되지 않았습니다.', 'No file selected.'), 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{current_user.id}_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            file.save(filepath)
            
            try:
                # 파일 읽기
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath)
                
                # 데이터셋 생성
                dataset = Dataset(
                    name=name,
                    description=description,
                    filename=file.filename,
                    file_path=filepath,
                    user_id=current_user.id,
                    row_count=len(df),
                    column_count=len(df.columns),
                    columns=df.columns.tolist()
                )
                db.session.add(dataset)
                db.session.flush()
                
                # 데이터 레코드 저장
                for _, row in df.iterrows():
                    record = DataRecord(
                        dataset_id=dataset.id,
                        data=row.to_dict()
                    )
                    db.session.add(record)
                
                db.session.commit()
                flash(get_message('데이터가 성공적으로 업로드되었습니다!', 'Data uploaded successfully!'), 'success')
                return redirect(url_for('view_dataset', dataset_id=dataset.id))
            
            except Exception as e:
                db.session.rollback()
                flash(get_message(f'파일 처리 중 오류가 발생했습니다: {str(e)}', f'Error processing file: {str(e)}'), 'danger')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(url_for('upload'))
        else:
            flash(get_message('허용되지 않는 파일 형식입니다.', 'Invalid file format.'), 'danger')
    
    return render_template('upload.html')

# 데이터셋 보기
@app.route('/dataset/<int:dataset_id>')
@login_required
def view_dataset(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash(get_message('접근 권한이 없습니다.', 'Access denied.'), 'danger')
        return redirect(url_for('dashboard'))
    
    records = DataRecord.query.filter_by(dataset_id=dataset_id).limit(100).all()
    data = [record.data for record in records]
    
    return render_template('view_dataset.html', dataset=dataset, data=data, columns=dataset.columns)

# 데이터 시각화
@app.route('/visualize/<int:dataset_id>')
@login_required
def visualize(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash(get_message('접근 권한이 없습니다.', 'Access denied.'), 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('visualize.html', dataset=dataset, columns=dataset.columns)

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
        
        if dataset.user_id != current_user.id:
            return jsonify({'error': get_message('접근 권한이 없습니다.', 'Access denied.')}), 403
        
        # 데이터 레코드 가져오기
        records = DataRecord.query.filter_by(dataset_id=dataset_id).all()
        if not records:
            return jsonify({'error': get_message('데이터가 없습니다.', 'No data available.')}), 400
        
        print(f"총 레코드 수 / Total records: {len(records)}")
        
        df = pd.DataFrame([record.data for record in records])
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
                        except:
                            # 날짜 변환 실패 -> 숫자 변환 시도
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
                        except:
                            pass
            
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
            for trace in fig_dict.get('data', []):
                # X축 데이터 처리
                if 'x' in trace:
                    x_data = trace['x']
                    # dict 형태의 바이너리 인코딩 체크
                    if isinstance(x_data, dict) and 'dtype' in x_data:
                        # 이미 바이너리로 인코딩된 경우 - 원본에서 가져오기
                        if df[x_column].dtype == 'datetime64[ns]':
                            # 날짜는 문자열로 변환 (타임스탬프가 아닌 ISO 형식)
                            trace['x'] = df[x_column].dt.strftime('%Y-%m-%d').tolist()
                            print(f"✅ X축 날짜를 문자열로 변환")
                        else:
                            trace['x'] = df[x_column].tolist()
                    elif hasattr(x_data, 'tolist'):
                        # numpy array나 pandas Series
                        # datetime인 경우 문자열로 변환
                        if df[x_column].dtype == 'datetime64[ns]':
                            trace['x'] = df[x_column].dt.strftime('%Y-%m-%d').tolist()
                            print(f"✅ X축 날짜를 문자열로 변환")
                        else:
                            trace['x'] = x_data.tolist()
                    elif not isinstance(x_data, list):
                        # 기타 iterable
                        trace['x'] = list(x_data)
                
                # Y축 데이터 처리
                if 'y' in trace:
                    y_data = trace['y']
                    # dict 형태의 바이너리 인코딩 체크
                    if isinstance(y_data, dict) and 'dtype' in y_data:
                        # 이미 바이너리로 인코딩된 경우 - 원본에서 가져오기
                        if df[y_column].dtype == 'datetime64[ns]':
                            # 날짜는 문자열로 변환 (타임스탬프가 아닌 ISO 형식)
                            trace['y'] = df[y_column].dt.strftime('%Y-%m-%d').tolist()
                            print(f"✅ Y축 날짜를 문자열로 변환")
                        else:
                            trace['y'] = df[y_column].tolist()
                        print(f"⚠️ Y축 바이너리 인코딩 감지 → 리스트로 변환")
                        print(f"변환된 Y 데이터 (처음 5개): {trace['y'][:5]}")
                    elif hasattr(y_data, 'tolist'):
                        # numpy array나 pandas Series
                        # datetime인 경우 문자열로 변환
                        if df[y_column].dtype == 'datetime64[ns]':
                            trace['y'] = df[y_column].dt.strftime('%Y-%m-%d').tolist()
                            print(f"✅ Y축 날짜를 문자열로 변환")
                        else:
                            trace['y'] = y_data.tolist()
                    elif not isinstance(y_data, list):
                        # 기타 iterable
                        trace['y'] = list(y_data)
                
                # 파이 차트용 labels 처리
                if 'labels' in trace:
                    labels_data = trace['labels']
                    if hasattr(labels_data, 'tolist'):
                        trace['labels'] = labels_data.tolist()
                        print(f"✅ 파이 차트 labels를 리스트로 변환")
                    elif not isinstance(labels_data, list):
                        trace['labels'] = list(labels_data)
                
                # 파이 차트용 values 처리
                if 'values' in trace:
                    values_data = trace['values']
                    if hasattr(values_data, 'tolist'):
                        trace['values'] = values_data.tolist()
                        print(f"✅ 파이 차트 values를 리스트로 변환")
                    elif not isinstance(values_data, list):
                        trace['values'] = list(values_data)

            
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
            return jsonify({'error': get_message(f'차트 생성 실패: {error_msg}', f'Chart creation failed: {error_msg}')}), 400
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 전체 오류 / General error: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': get_message(f'오류 발생: {error_msg}', f'Error occurred: {error_msg}')}), 400

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
        flash(get_message('파일이 선택되지 않았습니다.', 'No file selected.'), 'danger')
        return redirect(url_for('template_dashboard'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash(get_message('파일이 선택되지 않았습니다.', 'No file selected.'), 'danger')
        return redirect(url_for('template_dashboard'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{current_user.id}_template_{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        file.save(filepath)
        
        try:
            # 파일 읽기
            df = pd.read_excel(filepath)
            
            # 데이터셋 생성 (템플릿 플래그 추가)
            dataset = Dataset(
                name=f"Template Analysis {timestamp}",
                description="Template-based automated analysis",
                filename=file.filename,
                file_path=filepath,
                user_id=current_user.id,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.tolist(),
                is_template=True  # 템플릿 플래그
            )
            db.session.add(dataset)
            db.session.flush()
            
            # 데이터 레코드 저장
            for _, row in df.iterrows():
                record = DataRecord(
                    dataset_id=dataset.id,
                    data=row.to_dict()
                )
                db.session.add(record)
            
            db.session.commit()
            flash(get_message('템플릿이 성공적으로 업로드되었습니다!', 'Template uploaded successfully!'), 'success')
            return redirect(url_for('view_template_analysis', dataset_id=dataset.id))
        
        except Exception as e:
            db.session.rollback()
            flash(get_message(f'파일 처리 중 오류가 발생했습니다: {str(e)}', f'Error processing file: {str(e)}'), 'danger')
            if os.path.exists(filepath):
                os.remove(filepath)
            return redirect(url_for('template_dashboard'))
    else:
        flash(get_message('허용되지 않는 파일 형식입니다.', 'Invalid file format.'), 'danger')
        return redirect(url_for('template_dashboard'))

# 템플릿 기반 자동 분석 뷰
@app.route('/template/analysis/<int:dataset_id>')
@login_required
def view_template_analysis(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash(get_message('접근 권한이 없습니다.', 'Access denied.'), 'danger')
        return redirect(url_for('template_dashboard'))
    
    # 데이터 로드
    records = DataRecord.query.filter_by(dataset_id=dataset_id).all()
    df = pd.DataFrame([record.data for record in records])
    
    # 자동으로 차트 생성
    charts = generate_template_charts(df)
    
    # 주요 지표 계산
    metrics = calculate_metrics(df)
    
    return render_template('template_analysis.html', 
                         dataset=dataset, 
                         charts=charts, 
                         metrics=metrics,
                         data=df.head(100).to_dict('records'),
                         columns=df.columns.tolist())

# 템플릿 차트 자동 생성 함수
def generate_template_charts(df):
    charts = {}
    
    # 공통 레이아웃 설정
    common_layout = dict(
        height=380,
        margin=dict(l=60, r=40, t=60, b=60),
        font=dict(size=12, family="Arial, sans-serif"),
        title_font=dict(size=16, family="Arial, sans-serif"),
        hovermode='closest',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    
    try:
        # 날짜 컬럼 감지 및 변환
        date_column = None
        for col in df.columns:
            if '날짜' in col.lower() or 'date' in col.lower():
                df[col] = pd.to_datetime(df[col], errors='coerce')
                date_column = col
                break
        
        # 1. 일별 매출 추이 (라인 차트)
        if date_column and '매출액' in df.columns:
            daily_sales = df.groupby(date_column)['매출액'].sum().reset_index()
            fig1 = px.line(daily_sales, x=date_column, y='매출액',
                          title='일별 매출 추이', markers=True)
            fig1.update_layout(**common_layout)
            fig1.update_traces(line=dict(width=3), marker=dict(size=8))
            charts['daily_sales'] = json.dumps(fig1.to_dict())
        
        # 2. 지역별 매출 (바 차트)
        if '지역' in df.columns and '매출액' in df.columns:
            region_sales = df.groupby('지역')['매출액'].sum().reset_index()
            region_sales = region_sales.sort_values('매출액', ascending=False)
            fig2 = px.bar(region_sales, x='지역', y='매출액',
                         title='지역별 매출')
            fig2.update_layout(**common_layout)
            charts['region_sales'] = json.dumps(fig2.to_dict())
        
        # 3. 제품별 판매량 (파이 차트)
        if '제품' in df.columns:
            product_counts = df['제품'].value_counts().reset_index()
            product_counts.columns = ['제품', '판매건수']
            fig3 = px.pie(product_counts, names='제품', values='판매건수',
                         title='제품별 판매 비율')
            fig3.update_layout(**common_layout)
            fig3.update_traces(textposition='inside', textinfo='percent+label')
            charts['product_distribution'] = json.dumps(fig3.to_dict())
        
        # 4. 카테고리별 매출 (바 차트)
        if '카테고리' in df.columns and '매출액' in df.columns:
            category_sales = df.groupby('카테고리')['매출액'].sum().reset_index()
            fig4 = px.bar(category_sales, x='카테고리', y='매출액',
                         title='카테고리별 매출')
            fig4.update_layout(**common_layout)
            charts['category_sales'] = json.dumps(fig4.to_dict())
        
        # 5. 판매량 vs 매출액 (산점도)
        if '판매량' in df.columns and '매출액' in df.columns:
            fig5 = px.scatter(df, x='판매량', y='매출액',
                            title='판매량 vs 매출액 관계',
                            trendline="ols")
            fig5.update_layout(**common_layout)
            fig5.update_traces(marker=dict(size=8, opacity=0.6))
            charts['quantity_revenue'] = json.dumps(fig5.to_dict())
        
        # 6. 일별 평균 판매량 (라인 차트)
        if date_column and '판매량' in df.columns:
            daily_quantity = df.groupby(date_column)['판매량'].mean().reset_index()
            fig6 = px.line(daily_quantity, x=date_column, y='판매량',
                          title='일별 평균 판매량', markers=True)
            fig6.update_layout(**common_layout)
            fig6.update_traces(line=dict(width=3), marker=dict(size=8))
            charts['daily_quantity'] = json.dumps(fig6.to_dict())
        
    except Exception as e:
        print(f"차트 생성 오류: {e}")
    
    return charts

# 주요 지표 계산 함수
def calculate_metrics(df):
    metrics = {}
    
    try:
        if '매출액' in df.columns:
            metrics['total_revenue'] = int(df['매출액'].sum())
            metrics['avg_revenue'] = int(df['매출액'].mean())
        
        if '판매량' in df.columns:
            metrics['total_quantity'] = int(df['판매량'].sum())
            metrics['avg_quantity'] = round(df['판매량'].mean(), 1)
        
        if '비용' in df.columns and '매출액' in df.columns:
            total_cost = df['비용'].sum()
            total_revenue = df['매출액'].sum()
            metrics['total_profit'] = int(total_revenue - total_cost)
            metrics['profit_margin'] = round((metrics['total_profit'] / total_revenue) * 100, 1)
        
        metrics['total_records'] = len(df)
        
        if '지역' in df.columns:
            metrics['unique_regions'] = df['지역'].nunique()
        
        if '제품' in df.columns:
            metrics['unique_products'] = df['제품'].nunique()
        
    except Exception as e:
        print(f"지표 계산 오류: {e}")
    
    return metrics

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
        
        # 파일 저장
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"ocr_{timestamp}_{filename}"
        
        # UPLOAD_FOLDER 확인
        upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, unique_filename)
        file.save(filepath)
        
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
                
                # 데이터를 리스트로 변환
                data = df.values.tolist()
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
                
                flash(f'OCR 처리 실패: {error_msg}' if session.get('language') == 'ko' else f'OCR failed: {error_msg}', 'danger')
                return redirect(url_for('ocr_scan'))
        
        except Exception as e:
            print(f"❌ OCR 처리 오류: {e}")
            import traceback
            traceback.print_exc()
            
            ocr_session.status = 'failed'
            ocr_session.error_message = str(e)
            db.session.commit()
            
            flash(f'OCR 처리 중 오류가 발생했습니다: {str(e)}' if session.get('language') == 'ko' else f'OCR processing error: {str(e)}', 'danger')
            return redirect(url_for('ocr_scan'))
    
    except Exception as e:
        print(f"❌ 파일 업로드 오류: {e}")
        import traceback
        traceback.print_exc()
        
        flash('파일 업로드 중 오류가 발생했습니다.' if session.get('language') == 'ko' else 'File upload error.', 'danger')
        return redirect(url_for('ocr_scan'))
    
    # ✅ 이 부분은 절대 실행되지 않지만, 안전을 위해 추가
    return redirect(url_for('ocr_scan'))

@app.route('/ocr/verify/<int:session_id>')
@login_required
def ocr_verify(session_id):
    """OCR 데이터 검증 화면"""
    ocr_session = OCRSession.query.get_or_404(session_id)
    
    # 권한 확인
    if ocr_session.user_id != current_user.id:
        flash('접근 권한이 없습니다.' if session.get('language') == 'ko' else 'Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
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
        
        # 권한 확인
        if ocr_session.user_id != current_user.id:
            flash('접근 권한이 없습니다.' if session.get('language') == 'ko' else 'Access denied.', 'danger')
            return redirect(url_for('dashboard'))
        
        # 폼 데이터
        dataset_name = request.form.get('dataset_name')
        description = request.form.get('description', '')
        data_json = request.form.get('data')
        
        if not dataset_name or not data_json:
            flash('필수 항목을 입력해주세요.' if session.get('language') == 'ko' else 'Please fill in required fields.', 'danger')
            return redirect(url_for('ocr_verify', session_id=session_id))
        
        # JSON 파싱
        import json
        data_dict = json.loads(data_json)
        headers = data_dict.get('headers', [])
        rows = data_dict.get('rows', [])
        
        # DataFrame 생성
        df = pd.DataFrame(rows, columns=headers)
        
        # Excel 파일로 저장
        excel_filename = f"ocr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(dataset_name)}.xlsx"
        excel_filepath = os.path.join(app.config['UPLOAD_FOLDER'], excel_filename)
        df.to_excel(excel_filepath, index=False)
        
        # 데이터셋 생성
        dataset = Dataset(
            name=dataset_name,
            description=description,
            filename=excel_filename,
            file_path=excel_filepath,
            user_id=current_user.id,
            row_count=len(df),
            column_count=len(df.columns),
            columns=df.columns.tolist(),
            is_ocr=True
        )
        db.session.add(dataset)
        
        # DB에 데이터 저장
        for _, row in df.iterrows():
            record = DataRecord(
                dataset=dataset,
                data=row.to_dict()
            )
            db.session.add(record)
        
        db.session.commit()
        
        flash('데이터가 성공적으로 저장되었습니다!' if session.get('language') == 'ko' else 'Data saved successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        db.session.rollback()
        print(f"데이터 저장 오류: {e}")
        flash(f'데이터 저장 중 오류가 발생했습니다: {str(e)}' if session.get('language') == 'ko' else f'Error saving data: {str(e)}', 'danger')
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
    
    except Exception as e:
        print(f"템플릿 다운로드 오류: {str(e)}")
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
        
        # 파일 저장
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"template_{template_type}_{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        print(f"✅ 템플릿 파일 저장: {file_path}")
        
        # 데이터 읽기
        df = pd.read_csv(file_path)
        
        print(f"✅ 데이터 로드: {df.shape}")
        print(f"컬럼: {df.columns.tolist()}")
        
        # 데이터셋으로 저장 (옵션)
        if request.form.get('save_dataset') == 'true':
            template_info = TEMPLATES[template_type]
            dataset_name = f"{template_info['name_ko']} - {datetime.now().strftime('%Y-%m-%d')}"
            
            dataset = Dataset(
                user_id=current_user.id,
                name=dataset_name,
                filename=unique_filename,
                file_path=file_path,
                description=f"Template: {template_type}"
            )
            db.session.add(dataset)
            db.session.commit()
            
            print(f"✅ 데이터셋 저장: {dataset.id}")
        
        # 자동 분석 실행 (옵션)
        if request.form.get('auto_analysis') == 'true':
            # 분석 페이지로 리다이렉트 (데이터셋 ID와 함께)
            if 'dataset' in locals():
                return redirect(url_for('analysis', dataset_id=dataset.id))
            else:
                # 임시로 세션에 저장
                session['temp_file_path'] = file_path
                session['temp_template_type'] = template_type
                flash('파일이 업로드되었습니다. 분석을 시작하세요.' if session.get('language') == 'ko' else 'File uploaded. Start analysis.', 'success')
                return redirect(url_for('template_analysis'))
        else:
            flash('파일이 성공적으로 업로드되었습니다.' if session.get('language') == 'ko' else 'File uploaded successfully.', 'success')
            return redirect(url_for('template_analysis'))
    
    except Exception as e:
        print(f"❌ 템플릿 분석 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        
        flash(f'오류가 발생했습니다: {str(e)}' if session.get('language') == 'ko' else f'Error occurred: {str(e)}', 'danger')
        return redirect(url_for('template_analysis'))

####################
@app.route('/examples')
@login_required
def examples():
    """분석 예시 목록 페이지"""
    return render_template('examples.html')

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
