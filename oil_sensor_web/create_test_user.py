from app import db, User, app

with app.app_context():
    # 检查是否已有该用户
    existing_user = User.query.filter_by(username='test').first()
    if existing_user:
        print("测试用户 'test' 已存在，无需重复创建！")
    else:
        # ✅ 使用 set_password 方法设置密码
        test_user = User(username='test')
        test_user.set_password('123456')
        db.session.add(test_user)
        db.session.commit()
        print("测试用户创建成功！")
