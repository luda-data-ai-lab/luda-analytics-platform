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
            flash('파일이 선택되지 않았습니다.' if session.get('language') == 'ko' else 'No file selected.', 'danger')
            return redirect(url_for('ocr_scan'))
        
        file = request.files['file']
        if file.filename == '':
            flash('파일이 선택되지 않았습니다.' if session.get('language') == 'ko' else 'No file selected.', 'danger')
            return redirect(url_for('ocr_scan'))
        
        # 파일 저장
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ocr_{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # OCR 세션 생성
        ocr_session = OCRSession(
            user_id=current_user.id,
            filename=filename,
            file_path=filepath,
            status='processing'
        )
        db.session.add(ocr_session)
        db.session.commit()
        
        # OCR 처리
        from ocr_utils import process_ocr_document
        
        try:
            # 전처리 옵션
            preprocess = request.form.get('denoise') == 'on'
            
            # OCR 실행
            df = process_ocr_document(filepath, preprocess=preprocess)
            
            # 데이터를 리스트로 변환
            data = df.values.tolist()
            
            # 세션에 저장
            ocr_session.extracted_data = {
                'data': data,
                'columns': df.columns.tolist() if hasattr(df.columns, 'tolist') else list(range(len(data[0])))
            }
            ocr_session.status = 'completed'
            db.session.commit()
            
            return redirect(url_for('ocr_verify', session_id=ocr_session.id))
        
        except Exception as e:
            print(f"OCR 처리 오류: {e}")
            ocr_session.status = 'failed'
            ocr_session.error_message = str(e)
            db.session.commit()
            
            flash(f'OCR 처리 중 오류가 발생했습니다: {str(e)}' if session.get('language') == 'ko' else f'OCR processing error: {str(e)}', 'danger')
            return redirect(url_for('ocr_scan'))
    
    except Exception as e:
        print(f"파일 업로드 오류: {e}")
        flash('파일 업로드 중 오류가 발생했습니다.' if session.get('language') == 'ko' else 'File upload error.', 'danger')
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
