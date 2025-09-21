from typing import List, Optional

from fastapi import HTTPException,FastAPI,Query, Depends
from sqlmodel import Session,SQLModel,Field,Relationship,create_engine,select
import uuid
import datetime
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = "sqlite:///database.db"
engine = create_engine(DATABASE_URL, echo=True)

class User(SQLModel, table = True):
    id: uuid.UUID=Field(default_factory=uuid.uuid4,primary_key=True)
    tasks: List["Task"] = Relationship(back_populates="owner")

class Task(SQLModel, table = True):
    id: uuid.UUID=Field(default_factory=uuid.uuid4,primary_key = True)
    title: str
    description: str | None = None
    is_completed: bool = False
    due_date: datetime.date | None = None
    owner_id: Optional[uuid.UUID] = Field(default=None, foreign_key="user.id")
    
    # 型ヒントとしてOptional[User]を指定し、デフォルト値としてRelationship()を代入
    owner: Optional["User"] = Relationship(back_populates="tasks")

class TaskCreate(SQLModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime.date] = None

class TaskUpdate(SQLModel):
    title:Optional[str] = None
    description:Optional[str] = None
    is_completed:Optional[bool] = None
    due_date: Optional[datetime.date] = None

def get_session():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # アプリケーション起動時に実行する処理
    create_db_and_tables()
    yield
    # アプリケーション終了時に実行する処理 (今回はなし)
    print("INFO:     Application shutdown.")

app=FastAPI(lifespan = lifespan)

# フロントエンドのオリジン（場所）を指定
# 今回は全てのオリジンを許可する
origins = [
    "*", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # 全てのHTTPメソッドを許可
    allow_headers=["*"], # 全てのヘッダーを許可
)

async def get_current_user() -> User:
    # 本来はDBからトークンに対応するユーザーを取得する
    # ここでは学習のため、固定のユーザーを返す/作成する
    with Session(engine) as session:
        user = session.exec(select(User)).first()
        if not user:
            user = User()
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    
@app.post("/tasks/")
async def create_task(
    task: TaskCreate, 
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # 1. リクエストボディのデータを辞書に変換
    task_data = task.model_dump()
    
    # 2. サーバー側で追加したいデータを準備 (以前のupdate引数の役割)
    update_data = {"owner": current_user}

    # 3. 2つの辞書を結合し、それを元にモデルインスタンスを作成
    db_task = Task.model_validate({**task_data, **update_data})
    session.add(db_task)
    session.commit()
    session.refresh(db_task)
    return db_task

@app.get('/tasks/', response_model=List[Task])
def read_tasks(session: Session = Depends(get_session)):
    tasks = session.exec(select(Task)).all()
    return tasks

@app.get("/tasks/{task_id}", response_model=Task)
def read_task(task_id: uuid.UUID, session: Session = Depends(get_session)):
    """
    指定されたIDのタスクを1件取得する
    """
    task = session.get(Task, task_id)
    if not task:
        # タスクが見つからない場合は404エラーを返す
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.patch("/tasks/{task_id}", response_model=Task)
def update_task(
    task_id: uuid.UUID,
    task_update: TaskUpdate,
    session: Session = Depends(get_session)
):
    """
    指定されたIDのタスク情報を更新する
    """
    db_task = session.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 更新データ（TaskUpdate）を辞書に変換。Noneの項目は除外する。
    update_data = task_update.model_dump(exclude_unset=True)
    
    # 辞書の各項目を、元のデータベースオブジェクトにセットしていく
    for key, value in update_data.items():
        setattr(db_task, key, value)
        
    session.add(db_task)
    session.commit()
    session.refresh(db_task)
    return db_task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: uuid.UUID, session: Session = Depends(get_session)):
    """
    指定されたIDのタスクを削除する
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    session.delete(task)
    session.commit()
    
    # 成功メッセージを返す
    return {"ok": True, "message": "Task deleted successfully"}