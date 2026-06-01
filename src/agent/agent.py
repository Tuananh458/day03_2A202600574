import os
import re
import json
import ast
import inspect
from typing import List, Dict, Any, Optional, Generator
from src.core.llm_provider import LLMProvider
from src.telemetry.logger import logger

class ReActAgent:
    """
    Hệ thống ReAct Agent (Thought-Action-Observation) chuyên nghiệp dành cho
    Trợ lý thiết kế đề kiểm tra và quản lý Ngân hàng câu hỏi giáo dục.
    """
    
    def __init__(self, llm: LLMProvider, tools: List[Dict[str, Any]], max_steps: int = 7):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.history = []

    def get_system_prompt(self) -> str:
        """
        Xây dựng prompt hệ thống bằng tiếng Việt hướng dẫn Agent suy luận ReAct.
        """
        tool_descriptions = "\n".join([f"- {t['name']}: {t['description']}" for t in self.tools])
        
        return f"""Bạn là một AI Trợ lý giáo dục môn Toán/Lý cấp trung học. Bạn chỉ nói tiếng Việt và tuyệt đối tuân thủ định dạng ReAct.

BẠN CHỈ ĐƯỢC PHÉP TRẢ LỜI THEO CÚ PHÁP SAU:
Thought: Suy nghĩ bằng tiếng Việt của bạn về việc cần làm tiếp theo.
Action: tên_công_cụ(tham_số_1="giá_trị_1", tham_số_2=giá_trị_2, ...)
(Sau dòng Action này, bạn BẮT BUỘC phải dừng generation ngay lập tức, không tự viết Observation).

Hoặc khi đã hoàn thành đề thi:
Thought: Suy nghĩ cuối cùng bằng tiếng Việt.
Final Answer: Nội dung đề thi bằng tiếng Việt kèm đáp án và lời giải chi tiết.

CÁC CÔNG CỤ BẠN CÓ:
{tool_descriptions}

CÁC NGUYÊN TẮC BẮT BUỘC:
1. Luôn tra cứu chủ đề qua `get_curriculum_topics` trước để xác minh tính hợp lệ.
2. BẮT BUỘC phải gọi `fetch_questions_from_bank` để lấy câu hỏi Dễ và Trung bình trước khi tự sinh câu hỏi mới hoặc đưa ra câu trả lời cuối cùng. Bạn TUYỆT ĐỐI KHÔNG ĐƯỢC phép nhảy thẳng đến `Final Answer` mà chưa thực hiện cuộc gọi `fetch_questions_from_bank`.
3. Nếu ngân hàng thiếu câu hỏi, bạn phải tự biên soạn câu hỏi chuẩn lớp 12 và BẮT BUỘC gọi `save_question_to_bank` để lưu lại.
4. Mọi văn bản suy nghĩ (Thought) và câu trả lời phải viết bằng TIẾNG VIỆT. Tuyệt đối không viết tiếng Anh hay phân tích ngoài lề. Không thảo luận meta-reasoning về prompt.
5. Không được tự bịa ra Observation.
6. CỰC KỲ QUAN TRỌNG: Nếu `fetch_questions_from_bank` trả về mảng rỗng `[]` hoặc ít câu hơn số lượng yêu cầu, bạn KHÔNG ĐƯỢC gọi lại hàm đó với cùng tham số. Bạn BẮT BUỘC phải tự tạo câu hỏi mới bằng cách gọi `save_question_to_bank` ngay lập tức.

Ví dụ ReAct hợp lệ:
Thought: Tôi cần kiểm tra xem chủ đề 'Hàm số lũy thừa' có thuộc chương trình lớp 12 môn Toán không.
Action: get_curriculum_topics(grade=12, subject="Toán")
Observation: ["Hàm số lũy thừa", "Khối đa diện", "Tích phân", "Hình học tọa độ Oxyz"]
Thought: Chủ đề hợp lệ. Tôi cần tìm câu hỏi Dễ trong ngân hàng.
Action: fetch_questions_from_bank(topic="Hàm số lũy thừa", difficulty="Easy", num_questions=1)
Observation: [{{"id": "Q001", "question_text": "Tìm tập xác định D của hàm số y = (x - 1)^(-3).", "options": ["A. D = R", "B. D = R \\\\ {{1}}", "C. D = (1, +inf)", "D. D = (-inf, 1)"], "correct_answer": "B", "explanation": "..."}}]
Thought: Đã có 1 câu Dễ. Tôi tìm 2 câu Trung bình trong ngân hàng.
Action: fetch_questions_from_bank(topic="Hàm số lũy thừa", difficulty="Medium", num_questions=2)
Observation: [{{"id": "Q002", "question_text": "Tính đạo hàm...", "options": [...], "correct_answer": "A"}}]
Thought: Ngân hàng chỉ có 1 câu Trung bình, thiếu 1 câu. Tôi tự soạn câu Trung bình mới và lưu.
Action: save_question_to_bank(question_text="Cho y = (x^2 - 1)^e. Tìm tập xác định.", options=["A. R", "B. R \\\\ {{-1; 1}}", "C. (-inf; -1) U (1; +inf)", "D. (0; +inf)"], correct_answer="C", explanation="...", difficulty="Medium", topic="Hàm số lũy thừa", grade=12, subject="Toán")
Observation: SUCCESS: Đã lưu với ID = Q003.
Thought: Đã đủ 3 câu hỏi (Q001, Q002, Q003). Tôi sẽ lập đề thi hoàn chỉnh.
Final Answer: Dưới đây là đề kiểm tra môn Toán lớp 12 chủ đề 'Hàm số lũy thừa'...
"""



    def run(self, user_input: str) -> str:
        """
        Thực thi vòng lặp ReAct chính (Thought -> Action -> Observation -> Thought...).
        """
        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})
        
        # Xác định các độ khó được yêu cầu từ input của giáo viên để giám sát
        required_difficulties = set()
        user_input_lower = user_input.lower()
        if "dễ" in user_input_lower or "easy" in user_input_lower:
            required_difficulties.add("easy")
        if "trung bình" in user_input_lower or "medium" in user_input_lower:
            required_difficulties.add("medium")
        if "khó" in user_input_lower or "hard" in user_input_lower:
            required_difficulties.add("hard")

        fetched_difficulties = set()
        expected_saves = 0
        actual_saves = 0
        self.steps_data = [] # Lưu các bước chi tiết phục vụ cho Web UI

        current_prompt = f"Yêu cầu của giáo viên: {user_input}\n"
        steps = 0
        self.history = []

        while steps < self.max_steps:
            logger.log_event("AGENT_LOOP_START", {"step": steps + 1})
            
            # Gọi LLM sinh phản hồi (Thought + Action)
            response_dict = self.llm.generate(current_prompt, system_prompt=self.get_system_prompt())
            content = response_dict.get("content", "").strip()
            
            # Ghi nhận số liệu Telemetry đo lường hiệu năng
            from src.telemetry.metrics import tracker
            tracker.track_request(
                provider=response_dict.get("provider", "unknown"),
                model=self.llm.model_name,
                usage=response_dict.get("usage", {}),
                latency_ms=response_dict.get("latency_ms", 0)
            )
            
            logger.log_event("AGENT_STEP", {
                "step": steps + 1,
                "response": content
            })

            # Tách biệt Thought và Action phục vụ Telemetry Web
            thought_match = re.search(r"Thought:\s*([\s\S]+?)(?=\nAction:|\nFinal Answer:|\Z)", content, re.IGNORECASE)
            thought_text = thought_match.group(1).strip() if thought_match else ""
            if not thought_text and "Final Answer:" not in content and "Action:" not in content:
                thought_text = content
            
            # 1. Kiểm tra nếu có câu trả lời cuối cùng (Final Answer)
            final_match = re.search(r"Final Answer:\s*([\s\S]+)", content, re.IGNORECASE)
            if final_match:
                # Kiểm tra xem đã thực hiện đầy đủ cuộc gọi fetch đối với độ khó được yêu cầu chưa
                missing_diffs = required_difficulties - fetched_difficulties
                if missing_diffs:
                    missing_str = ", ".join([d.capitalize() for d in missing_diffs])
                    reminder = (
                        f"Hệ thống: Cảnh báo! Bạn chưa gọi công cụ `fetch_questions_from_bank` để truy vấn "
                        f"độ khó {missing_str} từ ngân hàng câu hỏi. Hãy thực hiện gọi công cụ này ngay."
                    )
                    current_prompt += f"\n{reminder}\n"
                    self.history.append({"role": "system", "content": reminder})
                    
                    self.steps_data.append({
                        "step": len(self.steps_data) + 1,
                        "thought": thought_text or "Nhận thấy thiếu sót cuộc gọi truy vấn ngân hàng.",
                        "action": "fetch_questions_from_bank (Hệ thống yêu cầu)",
                        "observation": reminder,
                        "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                    })
                    steps += 1
                    continue
                
                # Kiểm tra xem đã thực hiện đầy đủ cuộc gọi save đối với câu hỏi tự biên soạn chưa
                if actual_saves < expected_saves:
                    reminder = (
                        f"Hệ thống: Cảnh báo! Bạn chưa lưu đầy đủ các câu hỏi tự thiết kế vào ngân hàng câu hỏi "
                        f"(đã lưu: {actual_saves}/{expected_saves}). Hãy gọi công cụ `save_question_to_bank` để lưu lại."
                    )
                    current_prompt += f"\n{reminder}\n"
                    self.history.append({"role": "system", "content": reminder})
                    
                    self.steps_data.append({
                        "step": len(self.steps_data) + 1,
                        "thought": thought_text or "Nhận thấy thiếu sót cuộc gọi lưu trữ câu hỏi.",
                        "action": "save_question_to_bank (Hệ thống yêu cầu)",
                        "observation": reminder,
                        "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                    })
                    steps += 1
                    continue

                final_answer = final_match.group(1).strip()
                # Lưu lịch sử sạch trước khi kết thúc
                self.history.append({"role": "assistant", "content": content})
                
                self.steps_data.append({
                    "step": len(self.steps_data) + 1,
                    "thought": thought_text or "Hoàn thành biên soạn đề thi.",
                    "action": "Final Answer",
                    "observation": "",
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                })
                
                logger.log_event("AGENT_END", {"steps": steps + 1, "status": "success"})
                return final_answer
                
            # 2. Tìm kiếm hành động gọi công cụ (Action)
            action_info = self._find_action_call(content)
            if action_info:
                tool_name, args_str, end_pos = action_info
                
                # Cắt bỏ mọi phần text tự sinh dư thừa của LLM sau Action block để tránh ô nhiễm Prompt
                content = content[:end_pos].strip()
                
                logger.log_event("TOOL_CALL_DETECTED", {"tool": tool_name, "args_str": args_str})
                
                # Parse tham số của tool
                args = self._parse_arguments(args_str)
                
                # Thực thi công cụ
                observation = self._execute_tool(tool_name, args)
                
                logger.log_event("TOOL_EXECUTION_RESULT", {"tool": tool_name, "observation": observation})
                
                # Ghi nhận trạng thái truy vấn ngân hàng câu hỏi
                if tool_name == "fetch_questions_from_bank":
                    diff = args.get("difficulty", "").lower()
                    if diff:
                        fetched_difficulties.add(diff)
                    
                    try:
                        num_requested = int(args.get("num_questions", 1))
                    except Exception:
                        num_requested = 1
                        
                    # Phân tích xem có bao nhiêu câu hỏi thực sự được trả về
                    try:
                        parsed_obs = ast.literal_eval(observation)
                        if isinstance(parsed_obs, list):
                            actual_returned = len(parsed_obs)
                        else:
                            actual_returned = 0
                    except Exception:
                        actual_returned = observation.count("'id'") or observation.count('"id"')
                        
                    # Tính toán số lượng câu hỏi bị thiếu cần sinh mới và lưu
                    if actual_returned < num_requested:
                        expected_saves += (num_requested - actual_returned)

                # Ghi nhận trạng thái lưu câu hỏi mới
                elif tool_name == "save_question_to_bank":
                    if "SUCCESS" in observation or "success" in observation.lower():
                        actual_saves += 1
                
                self.steps_data.append({
                    "step": len(self.steps_data) + 1,
                    "thought": thought_text,
                    "action": f"{tool_name}({args_str})",
                    "observation": observation,
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                })

                # Lưu content đã sạch vào prompt và lịch sử
                current_prompt += f"\n{content}\n"
                self.history.append({"role": "assistant", "content": content})
                
                # Cộng dồn Observation vào Prompt và lịch sử
                observation_str = f"Observation: {observation}"
                current_prompt += f"\n{observation_str}\n"
                self.history.append({"role": "system", "content": observation_str})
                
                steps += 1
                continue
            else:
                # Nếu LLM không đưa ra Action cũng không đưa ra Final Answer
                # Lưu content hiện tại vào prompt và lịch sử
                current_prompt += f"\n{content}\n"
                self.history.append({"role": "assistant", "content": content})
                
                # Thêm hướng dẫn nhắc nhở vào prompt để ép LLM đưa ra Final Answer hoặc Action hợp lệ
                reminder = "Thought: Tôi cần đưa ra 'Action: tên_công_cụ(tham_số)' để lấy thông tin tiếp theo hoặc đưa ra 'Final Answer: <câu trả lời>' nếu đã hoàn thành."
                current_prompt += f"\n{reminder}\n"
                self.history.append({"role": "system", "content": reminder})
                logger.log_event("NO_ACTION_WARNING", {"step": steps + 1})

                self.steps_data.append({
                    "step": len(self.steps_data) + 1,
                    "thought": thought_text or content,
                    "action": "Không gọi công cụ",
                    "observation": reminder,
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                })
            
            steps += 1
            
        logger.log_event("AGENT_END", {"steps": steps, "status": "timeout_max_steps"})
        
        # Nếu hết số bước mà không tìm thấy Final Answer, thử trích xuất câu trả lời tốt nhất hoặc trả về lỗi
        final_attempt = re.findall(r"Thought:\s*([\s\S]+?)(?=\nAction:|\Z)", current_prompt)
        last_thought = final_attempt[-1].strip() if final_attempt else "Hết thời gian suy luận tối đa."
        return f"CẢNH BÁO: Agent đạt giới hạn {self.max_steps} bước lặp mà chưa hoàn thành bài thi.\n\nSuy nghĩ cuối cùng của Agent:\n{last_thought}"

    def _find_action_call(self, text: str) -> Optional[tuple[str, str, int]]:
        """
        Tìm kiếm và bóc tách lời gọi Action: tên_công_cụ(...) chính xác.
        Hỗ trợ cả trường hợp các tham số chứa ngoặc đơn lồng nhau (như công thức toán học).
        Trả về: (tên_công_cụ, chuỗi_tham_số, vị_trí_kết_thúc_của_action_block)
        """
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
            return tool_name, args_str, end_idx + 1
        else:
            return tool_name, text[start_idx:].strip(), len(text)

    def _parse_arguments(self, args_str: str) -> Dict[str, Any]:
        """
        Phân tích cú pháp tham số truyền vào công cụ động bằng AST (Abstract Syntax Tree) chuẩn xác.
        Hỗ trợ mọi định dạng: key=value, JSON, mảng, v.v.
        """
        args_str = args_str.strip()
        if not args_str:
            return {}
            
        # 1. Thử parse trực tiếp dưới dạng đối tượng JSON
        if args_str.startswith("{") and args_str.endswith("}"):
            try:
                return json.loads(args_str)
            except Exception:
                pass
                
        # 2. Sử dụng AST Parser để biên dịch các biểu thức Python an toàn
        try:
            # Bọc chuỗi tham số thành một lời gọi hàm giả lập hợp lệ
            parsed = ast.parse(f"func({args_str})")
            call_node = parsed.body[0].value
            args_dict = {}
            
            # Xử lý các đối số có khóa (keyword arguments) như: topic="Toán", grade=12
            for kw in call_node.keywords:
                args_dict[kw.arg] = ast.literal_eval(kw.value)
                
            # Xử lý đối số vị trí (positional arguments) nếu có
            for i, arg in enumerate(call_node.args):
                args_dict[f"arg_{i}"] = ast.literal_eval(arg)
                
            return args_dict
        except Exception as e:
            logger.info(f"AST parsing skipped for string '{args_str}'. Trying regex fallback. Detail: {e}")
            
            # 3. Bộ lọc Fallback Regex nếu LLM sinh mã lệch chuẩn
            args_dict = {}
            # Match kiểu key = "value" hoặc key = 12 hoặc key = [array]
            pattern = r'(\w+)\s*=\s*(?:(["\'])(.*?)\2|([\[\{].*?[\]\}])|([^,\s]+))'
            matches = re.findall(pattern, args_str)
            for match in matches:
                key = match[0]
                val = match[2] or match[3] or match[4]
                val = val.strip()
                
                if val.lower() == "true":
                    args_dict[key] = True
                elif val.lower() == "false":
                    args_dict[key] = False
                elif val.lower() == "none":
                    args_dict[key] = None
                else:
                    try:
                        args_dict[key] = ast.literal_eval(val)
                    except Exception:
                        args_dict[key] = val # Giữ nguyên string raw
            return args_dict

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Thực thi công cụ tương ứng dựa trên tên gọi và bộ tham số truyền vào từ Agent.
        """
        for tool in self.tools:
            if tool['name'] == tool_name:
                try:
                    func = tool['func']
                    sig = inspect.signature(func)
                    params = list(sig.parameters.keys())
                    
                    actual_kwargs = {}
                    
                    # Ánh xạ từ các đối số positional (arg_0, arg_1) sang các tham số thực tế của hàm
                    for k, v in args.items():
                        if k.startswith("arg_"):
                            try:
                                idx = int(k.split("_")[1])
                                if idx < len(params):
                                    actual_kwargs[params[idx]] = v
                            except Exception:
                                pass
                        else:
                            if k in params:
                                actual_kwargs[k] = v
                                
                    # Bổ sung các tham số còn thiếu nếu tên trùng khớp hoàn toàn
                    for p in params:
                        if p not in actual_kwargs and p in args:
                            actual_kwargs[p] = args[p]
                            
                    # Thực thi hàm
                    result = func(**actual_kwargs)
                    return str(result)
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}")
                    return f"ERROR: Lỗi hệ thống khi chạy công cụ {tool_name}: {str(e)}"
                    
        return f"ERROR: Công cụ {tool_name} không tồn tại trong danh sách của Agent."

    def run_stream(self, user_input: str) -> Generator[Dict[str, Any], None, None]:
        """
        Thực thi vòng lặp ReAct chính dưới dạng Generator để stream kết quả
        (Thought -> Action -> Observation -> Thought...).
        """
        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})
        
        # Xác định các độ khó được yêu cầu từ input của giáo viên để giám sát
        required_difficulties = set()
        user_input_lower = user_input.lower()
        if "dễ" in user_input_lower or "easy" in user_input_lower:
            required_difficulties.add("easy")
        if "trung bình" in user_input_lower or "medium" in user_input_lower:
            required_difficulties.add("medium")
        if "khó" in user_input_lower or "hard" in user_input_lower:
            required_difficulties.add("hard")

        fetched_difficulties = set()
        expected_saves = 0
        actual_saves = 0
        self.steps_data = [] # Lưu các bước chi tiết phục vụ cho Web UI

        current_prompt = f"Yêu cầu của giáo viên: {user_input}\n"
        steps = 0
        self.history = []

        while steps < self.max_steps:
            step_num = steps + 1
            logger.log_event("AGENT_LOOP_START", {"step": step_num})
            yield {"type": "step_start", "step": step_num}
            
            # Khởi tạo trạng thái parsing stream của bước này
            accumulated = ""
            mode = "searching_thought"
            thought_start_idx = 0
            streamed_thought_len = 0
            streamed_action_len = 0
            streamed_final_answer_len = 0
            action_start_idx = 0
            final_answer_start_idx = 0
            
            # Gọi LLM sinh phản hồi streaming
            llm_stream = self.llm.generate_stream(current_prompt, system_prompt=self.get_system_prompt())
            
            last_done_payload = None
            
            for chunk in llm_stream:
                if chunk["type"] == "chunk":
                    delta = chunk.get("content", "")
                    # Nếu model trả về delta rỗng nhưng có reasoning, chúng ta có thể mở rộng xử lý
                    # Tuy nhiên ở đây tập trung chính vào content
                    if not delta:
                        continue
                    
                    accumulated += delta
                    
                    # State machine
                    if mode == "searching_thought":
                        # Nhận diện Thought:
                        match_thought = re.search(r"Thought:\s*", accumulated, re.IGNORECASE)
                        if match_thought:
                            mode = "thought"
                            thought_start_idx = match_thought.end()
                        elif len(accumulated) >= 15 and "thought:" not in accumulated.lower():
                            # LLM không viết "Thought:", coi như bắt đầu thought luôn
                            mode = "thought"
                            thought_start_idx = 0
                            
                    if mode == "thought":
                        # Kiểm tra xem có Action: hoặc Final Answer: xuất hiện trong accumulated không
                        match_action = re.search(r"Action:\s*", accumulated, re.IGNORECASE)
                        match_final = re.search(r"Final Answer:\s*", accumulated, re.IGNORECASE)
                        
                        if match_action:
                            idx = match_action.start()
                            # Stream phần thought còn lại trước Action:
                            thought_content = accumulated[thought_start_idx:idx]
                            remaining_to_stream = thought_content[streamed_thought_len:]
                            if remaining_to_stream:
                                yield {"type": "thought_chunk", "step": step_num, "content": remaining_to_stream}
                                streamed_thought_len += len(remaining_to_stream)
                            
                            mode = "action"
                            action_start_idx = match_action.end()
                        elif match_final:
                            idx = match_final.start()
                            # Stream phần thought còn lại trước Final Answer:
                            thought_content = accumulated[thought_start_idx:idx]
                            remaining_to_stream = thought_content[streamed_thought_len:]
                            if remaining_to_stream:
                                yield {"type": "thought_chunk", "step": step_num, "content": remaining_to_stream}
                                streamed_thought_len += len(remaining_to_stream)
                            
                            mode = "final_answer"
                            final_answer_start_idx = match_final.end()
                        else:
                            # Stream thought có giữ lại buffer 20 ký tự để không stream lỡ header
                            thought_content = accumulated[thought_start_idx:]
                            if len(thought_content) > 20:
                                safe_length = len(thought_content) - 20
                                remaining_to_stream = thought_content[streamed_thought_len:safe_length]
                                if remaining_to_stream:
                                    yield {"type": "thought_chunk", "step": step_num, "content": remaining_to_stream}
                                    streamed_thought_len += len(remaining_to_stream)
                                    
                    elif mode == "action":
                        # Đang trong Action, stream phần Action
                        action_content = accumulated[action_start_idx:]
                        remaining_to_stream = action_content[streamed_action_len:]
                        if remaining_to_stream:
                            yield {"type": "action_chunk", "step": step_num, "content": remaining_to_stream}
                            streamed_action_len += len(remaining_to_stream)
                            
                    elif mode == "final_answer":
                        # Đang trong Final Answer, stream phần Final Answer
                        final_content = accumulated[final_answer_start_idx:]
                        remaining_to_stream = final_content[streamed_final_answer_len:]
                        if remaining_to_stream:
                            yield {"type": "final_answer_chunk", "step": step_num, "content": remaining_to_stream}
                            streamed_final_answer_len += len(remaining_to_stream)
                            
                elif chunk["type"] == "done":
                    last_done_payload = chunk
                    
            # Khi stream LLM kết thúc, dọn dẹp các ký tự cuối cùng chưa được stream
            if mode == "thought":
                thought_content = accumulated[thought_start_idx:]
                remaining_to_stream = thought_content[streamed_thought_len:]
                if remaining_to_stream:
                    yield {"type": "thought_chunk", "step": step_num, "content": remaining_to_stream}
            elif mode == "action":
                action_content = accumulated[action_start_idx:]
                remaining_to_stream = action_content[streamed_action_len:]
                if remaining_to_stream:
                    yield {"type": "action_chunk", "step": step_num, "content": remaining_to_stream}
            elif mode == "final_answer":
                final_content = accumulated[final_answer_start_idx:]
                remaining_to_stream = final_content[streamed_final_answer_len:]
                if remaining_to_stream:
                    yield {"type": "final_answer_chunk", "step": step_num, "content": remaining_to_stream}
            
            content = last_done_payload.get("content", "").strip() if last_done_payload else accumulated.strip()
            
            # Ghi nhận số liệu Telemetry đo lường hiệu năng
            from src.telemetry.metrics import tracker
            tracker.track_request(
                provider=last_done_payload.get("provider", "unknown") if last_done_payload else "openai",
                model=self.llm.model_name,
                usage=last_done_payload.get("usage", {}) if last_done_payload else {},
                latency_ms=last_done_payload.get("latency_ms", 0) if last_done_payload else 0
            )
            
            logger.log_event("AGENT_STEP", {
                "step": step_num,
                "response": content
            })

            # Trích xuất thought_text
            thought_match = re.search(r"Thought:\s*([\s\S]+?)(?=\nAction:|\nFinal Answer:|\Z)", content, re.IGNORECASE)
            thought_text = thought_match.group(1).strip() if thought_match else ""
            if not thought_text and "Final Answer:" not in content and "Action:" not in content:
                thought_text = content
                
            # 1. Kiểm tra nếu có câu trả lời cuối cùng (Final Answer)
            final_match = re.search(r"Final Answer:\s*([\s\S]+)", content, re.IGNORECASE)
            if final_match:
                # Kiểm tra xem đã thực hiện đầy đủ cuộc gọi fetch đối với độ khó được yêu cầu chưa
                missing_diffs = required_difficulties - fetched_difficulties
                if missing_diffs:
                    missing_str = ", ".join([d.capitalize() for d in missing_diffs])
                    reminder = (
                        f"Hệ thống: Cảnh báo! Bạn chưa gọi công cụ `fetch_questions_from_bank` để truy vấn "
                        f"độ khó {missing_str} từ ngân hàng câu hỏi. Hãy thực hiện gọi công cụ này ngay."
                    )
                    current_prompt += f"\n{reminder}\n"
                    self.history.append({"role": "system", "content": reminder})
                    
                    self.steps_data.append({
                        "step": len(self.steps_data) + 1,
                        "thought": thought_text or "Nhận thấy thiếu sót cuộc gọi truy vấn ngân hàng.",
                        "action": "fetch_questions_from_bank (Hệ thống yêu cầu)",
                        "observation": reminder,
                        "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                    })
                    yield {
                        "type": "warning",
                        "step": step_num,
                        "message": reminder,
                        "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                    }
                    steps += 1
                    continue
                
                # Kiểm tra xem đã thực hiện đầy đủ cuộc gọi save đối với câu hỏi tự biên soạn chưa
                if actual_saves < expected_saves:
                    reminder = (
                        f"Hệ thống: Cảnh báo! Bạn chưa lưu đầy đủ các câu hỏi tự thiết kế vào ngân hàng câu hỏi "
                        f"(đã lưu: {actual_saves}/{expected_saves}). Hãy gọi công cụ `save_question_to_bank` để lưu lại."
                    )
                    current_prompt += f"\n{reminder}\n"
                    self.history.append({"role": "system", "content": reminder})
                    
                    self.steps_data.append({
                        "step": len(self.steps_data) + 1,
                        "thought": thought_text or "Nhận thấy thiếu sót cuộc gọi lưu trữ câu hỏi.",
                        "action": "save_question_to_bank (Hệ thống yêu cầu)",
                        "observation": reminder,
                        "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                    })
                    yield {
                        "type": "warning",
                        "step": step_num,
                        "message": reminder,
                        "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                    }
                    steps += 1
                    continue

                final_answer = final_match.group(1).strip()
                # Lưu lịch sử sạch trước khi kết thúc
                self.history.append({"role": "assistant", "content": content})
                
                self.steps_data.append({
                    "step": len(self.steps_data) + 1,
                    "thought": thought_text or "Hoàn thành biên soạn đề thi.",
                    "action": "Final Answer",
                    "observation": "",
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                })
                
                logger.log_event("AGENT_END", {"steps": steps + 1, "status": "success"})
                
                # Trả về kết quả cuối cùng qua sự kiện done
                yield {
                    "type": "done",
                    "response": final_answer,
                    "steps": self.steps_data,
                    "telemetry": self._get_total_telemetry()
                }
                return

            # 2. Tìm kiếm hành động gọi công cụ (Action)
            action_info = self._find_action_call(content)
            if action_info:
                tool_name, args_str, end_pos = action_info
                
                # Cắt bỏ mọi phần text tự sinh dư thừa của LLM sau Action block để tránh ô nhiễm Prompt
                content = content[:end_pos].strip()
                
                logger.log_event("TOOL_CALL_DETECTED", {"tool": tool_name, "args_str": args_str})
                
                # Parse tham số của tool
                args = self._parse_arguments(args_str)
                
                # Yield sự kiện tool_start
                yield {
                    "type": "tool_start",
                    "step": step_num,
                    "tool": tool_name,
                    "args": args_str
                }
                
                # Thực thi công cụ
                observation = self._execute_tool(tool_name, args)
                
                logger.log_event("TOOL_EXECUTION_RESULT", {"tool": tool_name, "observation": observation})
                
                # Ghi nhận trạng thái truy vấn ngân hàng câu hỏi
                if tool_name == "fetch_questions_from_bank":
                    diff = args.get("difficulty", "").lower()
                    if diff:
                        fetched_difficulties.add(diff)
                    
                    try:
                        num_requested = int(args.get("num_questions", 1))
                    except Exception:
                        num_requested = 1
                        
                    try:
                        parsed_obs = ast.literal_eval(observation)
                        if isinstance(parsed_obs, list):
                            actual_returned = len(parsed_obs)
                        else:
                            actual_returned = 0
                    except Exception:
                        actual_returned = observation.count("'id'") or observation.count('"id"')
                        
                    if actual_returned < num_requested:
                        expected_saves += (num_requested - actual_returned)

                # Ghi nhận trạng thái lưu câu hỏi mới
                elif tool_name == "save_question_to_bank":
                    if "SUCCESS" in observation or "success" in observation.lower():
                        actual_saves += 1
                
                self.steps_data.append({
                    "step": len(self.steps_data) + 1,
                    "thought": thought_text,
                    "action": f"{tool_name}({args_str})",
                    "observation": observation,
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                })
                
                # Yield sự kiện tool_result
                yield {
                    "type": "tool_result",
                    "step": step_num,
                    "tool": tool_name,
                    "observation": observation,
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                }

                # Lưu content đã sạch vào prompt và lịch sử
                current_prompt += f"\n{content}\n"
                self.history.append({"role": "assistant", "content": content})
                
                # Cộng dồn Observation vào Prompt và lịch sử
                observation_str = f"Observation: {observation}"
                current_prompt += f"\n{observation_str}\n"
                self.history.append({"role": "system", "content": observation_str})
                
                steps += 1
                continue
            else:
                # Nếu LLM không đưa ra Action cũng không đưa ra Final Answer
                current_prompt += f"\n{content}\n"
                self.history.append({"role": "assistant", "content": content})
                
                reminder = "Thought: Tôi cần đưa ra 'Action: tên_công_cụ(tham_số)' để lấy thông tin tiếp theo hoặc đưa ra 'Final Answer: <câu trả lời>' nếu đã hoàn thành."
                current_prompt += f"\n{reminder}\n"
                self.history.append({"role": "system", "content": reminder})
                logger.log_event("NO_ACTION_WARNING", {"step": step_num})

                self.steps_data.append({
                    "step": len(self.steps_data) + 1,
                    "thought": thought_text or content,
                    "action": "Không gọi công cụ",
                    "observation": reminder,
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                })
                
                yield {
                    "type": "warning",
                    "step": step_num,
                    "message": reminder,
                    "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                }
            
            steps += 1
            
        logger.log_event("AGENT_END", {"steps": steps, "status": "timeout_max_steps"})
        
        final_attempt = re.findall(r"Thought:\s*([\s\S]+?)(?=\nAction:|\Z)", current_prompt)
        last_thought = final_attempt[-1].strip() if final_attempt else "Hết thời gian suy luận tối đa."
        limit_msg = f"CẢNH BÁO: Agent đạt giới hạn {self.max_steps} bước lặp mà chưa hoàn thành bài thi.\n\nSuy nghĩ cuối cùng của Agent:\n{last_thought}"
        
        yield {
            "type": "done",
            "response": limit_msg,
            "steps": self.steps_data,
            "telemetry": self._get_total_telemetry()
        }

    def _get_total_telemetry(self) -> Dict[str, Any]:
        from src.telemetry.metrics import tracker
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        total_latency = 0
        total_cost = 0.0
        
        for metric in tracker.session_metrics:
            prompt_tokens += metric.get("prompt_tokens", 0)
            completion_tokens += metric.get("completion_tokens", 0)
            total_tokens += metric.get("total_tokens", 0)
            total_latency += metric.get("latency_ms", 0)
            total_cost += metric.get("cost_estimate", 0.0)
            
        return {
            "latency_ms": total_latency,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_estimate": total_cost,
            "steps": len(tracker.session_metrics)
        }
