# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Hoàng Kim Tuấn Anh
- **Student ID**: 2A202600574
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)
1.  **Thiết kế Công cụ Giáo dục (`src/tools/quiz_tools.py`)**:
    *   Xây dựng cơ sở dữ liệu Ngân hàng câu hỏi trắc nghiệm dưới dạng tệp tin JSON [data/question_bank.json](file:///d:/solution/Day-3-Lab-Chatbot-vs-react-agent/data/question_bank.json) để đảm bảo khả năng ghi nhận và lưu trữ câu hỏi lâu dài.
    *   Viết mã nguồn cho các công cụ: `get_curriculum_topics` (tra cứu chương trình học), `fetch_questions_from_bank` (truy vấn câu hỏi có sẵn) và `save_question_to_bank` (lưu câu hỏi mới).
2.  **Bộ phân tích dấu ngoặc lồng nhau động (`src/agent/agent.py`)**:
    *   Tự viết thuật toán Character Scan trong hàm `_find_action_call` để bóc tách lời gọi `Action` chứa các tham số có dấu ngoặc lồng nhau (như công thức toán học kiểu `(x^2 - 4)^0.5` hoặc khoảng giá trị `(-inf, -2)`).
    *   Tận dụng thư viện `ast` (Abstract Syntax Tree) trong hàm `_parse_arguments` để phân tích các đối số kiểu mảng hoặc kiểu phức tạp một cách an toàn chuẩn công nghiệp.
3.  **Tương thích OpenRouter & Quản lý Token Quota (`src/core/openai_provider.py`)**:
    *   Lập trình cơ chế tự nhận diện khóa `sk-or-` của OpenRouter để đổi endpoint và chuyển đổi model mapping thích hợp.
    *   Giới hạn `max_tokens=4096` để vừa tránh lỗi cạn tín dụng (Credit Quota / Payment Required) đặc thù của OpenRouter, vừa đảm bảo câu trả lời không bị cắt cụt giữa chừng khi sinh nội dung đề thi dài.

### Code Highlight: Thuật toán quét và bóc tách cặp ngoặc lồng nhau
```python
def _find_action_call(self, text: str) -> Optional[tuple[str, str]]:
    match = re.search(r"Action:\s*(\w+)\(", text, re.IGNORECASE)
    if not match:
        return None
        
    tool_name = match.group(1).strip()
    start_idx = match.end()
    
    paren_count = 1
    end_idx = start_idx
    in_string = False
    string_char = None
    escaped = False
    
    while end_idx < len(text):
        char = text[end_idx]
        if escaped:
            escaped = False
            end_idx += 1
            continue
        if char == '\\':
            escaped = True
            end_idx += 1
            continue
        if char in ('"', "'"):
            if not in_string:
                in_string = True
                string_char = char
            elif string_char == char:
                in_string = False
                string_char = None
                
        if not in_string:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count == 0:
                    break
        end_idx += 1
        
    if paren_count == 0:
        args_str = text[start_idx:end_idx].strip()
        return tool_name, args_str
    else:
        return tool_name, text[start_idx:].strip()
```

---

## II. Debugging Case Study (10 Points)

Trong suốt quá trình thực nghiệm phát triển Agent v1, tôi đã đối mặt và giải quyết triệt để **2 sự cố gỡ lỗi kinh điển** bằng cách phân tích nhật ký telemetry lưu tại thư mục [logs/](file:///d:/solution/Day-3-Lab-Chatbot-vs-react-agent/logs/):

### Case Study 1: LLM tự ảo tưởng kết quả công cụ (Observation Hallucination / Loop Bypass)
*   **Mô tả lỗi**: Khi chạy Agent v1, mặc dù LLM đưa ra đúng cú pháp `Action: save_question_to_bank(...)` tại Bước 4, nó không dừng lại mà tiếp tục tự sinh luôn dòng `Observation: SUCCESS...` và tự đưa ra `Final Answer: ...` trong cùng một lượt phản hồi dài 1030 tokens. Điều này khiến mã Python loop bóc tách được Final Answer luôn và kết thúc tiến trình mà **chưa bao giờ thực sự gọi hay lưu câu hỏi** vào ngân hàng câu hỏi.
*   **Nguồn Log**: Trích từ [2026-06-01.log](file:///d:/solution/Day-3-Lab-Chatbot-vs-react-agent/logs/2026-06-01.log):
    ```json
    {"timestamp": "2026-06-01T05:16:43.866545", "event": "LLM_METRIC", "data": {"prompt_tokens": 2302, "completion_tokens": 1030, "total_tokens": 3332}}
    {"timestamp": "2026-06-01T05:16:43.866743", "event": "AGENT_STEP", "data": {"step": 4, "response": "Thought: ... \nAction: save_question_to_bank(...)\nObservation: SUCCESS: Đã lưu... \nFinal Answer: ..."}}
    ```
*   **Chẩn đoán**: LLM của OpenAI (`gpt-4o`) hoạt động theo cơ chế Autoregressive (dự đoán từ tiếp theo) nên nếu không có giới hạn, nó sẽ cố dự đoán và tự trả lời luôn vai trò của hệ thống (`Observation:`). Nguyên nhân là do provider kết nối OpenAI thiếu cơ chế ngăn chặn (`stop sequence`).
*   **Giải pháp**: Tôi đã cấu hình bổ sung tham số `stop=["Observation:", "observation:", "Observation: "]` trong hàm tạo Chat Completion của file [openai_provider.py](file:///d:/solution/Day-3-Lab-Chatbot-vs-react-agent/src/core/openai_provider.py). Nhờ vậy, ngay sau khi xuất ra lời gọi hành động `Action:...`, mô hình bắt buộc phải dừng thế hệ và nhường quyền kiểm soát lại cho vòng lặp Python thực thi công cụ thật.

### Case Study 2: Trích xuất tham số thất bại do công thức toán học lồng dấu ngoặc đơn
*   **Mô tả lỗi**: Khi Agent biên soạn một câu hỏi Toán chứa công thức như `y = (x^2 - 4)^0.5` hoặc mảng `[-2, 2]`, bộ phân tích cú pháp cũ sử dụng biểu thức chính quy Regex dạng `Action: (\w+)\((.*?)\)` bị hiểu nhầm dấu đóng ngoặc của công thức toán học chính là dấu đóng ngoặc của hàm `save_question_to_bank()`. Hệ quả là chuỗi đối số bị cắt cụt ở giữa chừng, gây ra lỗi thiếu tham số nghiêm trọng từ hàm Python.
*   **Nguồn Log**:
    ```text
    TOOL_CALL_DETECTED: {"tool": "save_question_to_bank", "args_str": "question_text=\"Cho hàm số y = (x^2 - 4"}
    TypeError: save_question_to_bank() missing 7 required positional arguments: 'options', 'correct_answer', 'explanation', 'difficulty', 'topic', 'grade', and 'subject'
    ```
*   **Chẩn đoán**: Các công cụ biểu thức chính quy (Regex) không có khả năng ghi nhớ trạng thái (Stateless) nên không thể xử lý tốt các bài toán khớp cặp ngoặc lồng nhau (Context-free Grammar).
*   **Giải pháp**: Tôi đã viết hàm khớp ngoặc động nâng cao `_find_action_call` bằng cơ chế duyệt từng ký tự (Character Scan), đồng thời bỏ qua ngoặc đơn lồng trong các chuỗi được bao quanh bởi dấu nháy kép/đơn. Giải pháp này giúp bóc tách chính xác 100% tất cả các tham số phức tạp mà không bị lỗi.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

1.  **Về khả năng tư duy (Reasoning)**:
    *   Một LLM Chatbot đơn thuần hoạt động theo cơ chế phản xạ nhanh (System 1) - trả lời câu hỏi trực tiếp dựa trên trọng số xác suất, dễ dẫn đến ảo tưởng kiến thức (hallucination) khi gặp câu hỏi phức tạp.
    *   Ngược lại, ReAct Agent hoạt động theo cơ chế tư duy chậm và chủ động (System 2). Việc bắt buộc phải ghi ra `Thought` giúp phân rã bài toán phức tạp thành các bước nhỏ hơn, suy luận logic trước khi hành động, giúp kết quả có tính chính xác, thực tế và có tính kiểm chứng cao.
2.  **Về độ tin cậy (Reliability)**:
    *   Mặc dù ReAct Agent rất mạnh mẽ nhưng hoạt động kém hiệu quả và tốn kém hơn Chatbot trong các câu hỏi mang tính chất trò chuyện đơn giản (chào hỏi, hỏi thông tin phổ thông). Trong các tình huống này, Agent vẫn phải trải qua các bước `Thought` không cần thiết, làm tăng đáng kể **độ trễ (latency)** và **chi phí API (cost)**.
    *   Ngoài ra, nếu bộ parser hoặc stop sequence thiết lập không chuẩn, Agent có thể rơi vào vòng lặp vô hạn (Infinite Loop) hoặc crash hệ thống, điều mà một Chatbot thông thường không bao giờ gặp phải.
3.  **Về phản hồi môi trường (Observation)**:
    *   Kết quả từ môi trường (`Observation`) hoạt động như một mỏ neo thực tế. Nó sửa sai cho Agent khi đưa ra giả định không đúng (ví dụ: Agent nghĩ một chủ đề có sẵn trong ngân hàng, nhưng khi công cụ trả về danh sách rỗng, Agent lập tức chuyển hướng sang tự thiết kế câu hỏi mới). Môi trường phản hồi giúp Agent có khả năng tự sửa lỗi (Self-Correction) linh hoạt.

---

## IV. Future Improvements (5 Points)

Để nâng cấp trợ lý giáo dục này lên quy mô Production (thương mại hóa thực tế), tôi đề xuất 3 cải tiến quan trọng:

1.  **Hạ tầng bất đồng bộ & Xử lý song song (Scalability)**:
    *   Khi giáo viên yêu cầu đề thi quy mô lớn (50-100 câu hỏi), việc gọi công cụ và tạo câu hỏi tuần tự sẽ gây tắc nghẽn nghiêm trọng. Cần áp dụng mô hình lập trình bất đồng bộ (`asyncio`) kết hợp xử lý hàng đợi (Queue) để sinh nhiều câu hỏi song song và lưu vào Database cùng lúc.
2.  **Cơ chế kiểm duyệt & Guardrails giáo dục (Safety)**:
    *   Cần xây dựng một lớp Supervisor Agent (Tác tử giám sát) sử dụng mô hình LLM nhỏ hơn, chuyên biệt để kiểm duyệt nội dung câu hỏi mới sinh, đảm bảo không vi phạm các tiêu chuẩn chính trị, đạo đức, và có ngôn từ phù hợp với lứa tuổi học sinh trước khi lưu vào ngân hàng câu hỏi chung.
3.  **Tìm kiếm ngữ nghĩa thông minh & Caching (Performance)**:
    *   Tích hợp Vector Database (như Pinecone hoặc ChromaDB) cho công cụ `fetch_questions_from_bank` để tìm kiếm câu hỏi theo độ tương đồng ngữ nghĩa (Semantic Search), thay vì chỉ so khớp chuỗi ký tự cứng nhắc. Đồng thời ứng dụng cơ chế lưu bộ nhớ đệm (Caching) các cấu trúc đề thi phổ biến để giảm thiểu tối đa chi phí gọi API LLM.
