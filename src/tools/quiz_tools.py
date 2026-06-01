import os
import json
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "question_bank.json")

# Mock Curriculum database
CURRICULUM_DATA = {
    12: {
        "Toán": ["Hàm số lũy thừa", "Khối đa diện", "Tích phân", "Hình học tọa độ Oxyz"],
        "Vật lý": ["Dao động cơ", "Sóng cơ và sóng âm", "Dòng điện xoay chiều", "Dao động và sóng điện từ"]
    },
    11: {
        "Toán": ["Hàm số lượng giác", "Giới hạn và liên tục", "Đạo hàm", "Quan hệ song song"],
        "Vật lý": ["Dao động điều hòa", "Sóng cơ học", "Điện trường", "Dòng điện không đổi"]
    },
    10: {
        "Toán": ["Mệnh đề và tập hợp", "Hàm số bậc hai", "Hệ thức lượng trong tam giác", "Vectơ"],
        "Vật lý": ["Động học", "Động lực học", "Năng lượng công", "Động lượng"]
    }
}

def get_curriculum_topics(grade: int, subject: str) -> List[str]:
    """
    Tra cứu danh sách các chủ đề chính thức theo chương trình của Bộ Giáo dục cho khối lớp và môn học chỉ định.
    Args:
        grade: Khối lớp (ví dụ: 10, 11, 12).
        subject: Môn học (ví dụ: 'Toán', 'Vật lý').
    Returns:
        Danh sách các chủ đề hợp lệ.
    """
    grade_data = CURRICULUM_DATA.get(int(grade))
    if not grade_data:
        return []
    return grade_data.get(subject, [])

def fetch_questions_from_bank(topic: str, difficulty: str, num_questions: int) -> List[Dict[str, Any]]:
    """
    Lấy danh sách các câu hỏi trắc nghiệm có sẵn trong Ngân hàng câu hỏi dựa trên chủ đề và độ khó.
    Args:
        topic: Tên chủ đề học tập (ví dụ: 'Hàm số lũy thừa').
        difficulty: Độ khó của câu hỏi (Easy, Medium, Hard).
        num_questions: Số lượng câu hỏi muốn lấy tối đa.
    Returns:
        Danh sách các câu hỏi phù hợp dưới dạng JSON.
    """
    if not os.path.exists(DB_FILE):
        return []
    
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            questions = json.load(f)
    except Exception:
        return []
        
    filtered = [
        q for q in questions 
        if q.get("topic", "").lower() == topic.lower() 
        and q.get("difficulty", "").lower() == difficulty.lower()
    ]
    return filtered[:int(num_questions)]

def save_question_to_bank(
    question_text: str, 
    options: List[str], 
    correct_answer: str, 
    explanation: str, 
    difficulty: str, 
    topic: str, 
    grade: int,
    subject: str
) -> str:
    """
    Lưu một câu hỏi trắc nghiệm mới được thiết kế vào Ngân hàng câu hỏi.
    Args:
        question_text: Nội dung câu hỏi.
        options: Danh sách 4 phương án trắc nghiệm dạng ['A. ...', 'B. ...', 'C. ...', 'D. ...'].
        correct_answer: Phương án đúng (A, B, C, hoặc D).
        explanation: Lời giải thích chi tiết đáp án.
        difficulty: Độ khó (Easy, Medium, Hard).
        topic: Chủ đề bài học.
        grade: Khối lớp (10, 11, 12).
        subject: Môn học (Toán, Vật lý).
    Returns:
        Mã ID của câu hỏi mới lưu và thông báo thành công.
    """
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    questions = []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                questions = json.load(f)
        except Exception:
            questions = []
            
    # Generate new ID
    if questions:
        last_id = questions[-1].get("id", "Q000")
        try:
            num = int(last_id[1:]) + 1
            new_id = f"Q{num:03d}"
        except Exception:
            new_id = f"Q{len(questions)+1:03d}"
    else:
        new_id = "Q001"
        
    new_q = {
        "id": new_id,
        "grade": int(grade),
        "subject": subject,
        "topic": topic,
        "difficulty": difficulty,
        "question_text": question_text,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation
    }
    
    questions.append(new_q)
    
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
        
    return f"SUCCESS: Đã lưu câu hỏi mới vào ngân hàng thành công với ID = {new_id}."

# Metadata cho Agent hiểu cấu trúc và tác dụng của từng tool
TOOLS_METADATA = [
    {
        "name": "get_curriculum_topics",
        "description": "get_curriculum_topics(grade, subject) - Tra cứu danh sách các chủ đề chính thức theo chương trình của Bộ Giáo dục cho khối lớp (10, 11, 12) và môn học ('Toán', 'Vật lý'). Trả về danh sách chuỗi.",
        "func": get_curriculum_topics
    },
    {
        "name": "fetch_questions_from_bank",
        "description": "fetch_questions_from_bank(topic, difficulty, num_questions) - Lấy danh sách các câu hỏi trắc nghiệm có sẵn trong Ngân hàng câu hỏi dựa trên chủ đề (ví dụ: 'Hàm số lũy thừa'), độ khó ('Easy', 'Medium', 'Hard') và số lượng câu hỏi muốn lấy tối đa. Trả về danh sách câu hỏi có cấu trúc.",
        "func": fetch_questions_from_bank
    },
    {
        "name": "save_question_to_bank",
        "description": "save_question_to_bank(question_text, options, correct_answer, explanation, difficulty, topic, grade, subject) - Lưu một câu hỏi trắc nghiệm mới thiết kế vào Ngân hàng câu hỏi để tái sử dụng. 'options' là danh sách 4 chuỗi chứa phương án. 'correct_answer' là 'A', 'B', 'C' hoặc 'D'. 'grade' là số nguyên. Trả về chuỗi thông báo kết quả.",
        "func": save_question_to_bank
    }
]
