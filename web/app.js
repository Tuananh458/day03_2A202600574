document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages-container");
    const providerSelect = document.getElementById("provider-select");
    const modelSelect = document.getElementById("model-select");
    const btnClearChat = document.getElementById("btn-clear-chat");
    const btnSubmitChat = document.getElementById("btn-submit-chat");
    const btnText = btnSubmitChat.querySelector(".btn-text");
    const btnSpinner = btnSubmitChat.querySelector(".btn-spinner");
    
    // Telemetry Elements
    const metricLatency = document.getElementById("metric-latency");
    const metricTokens = document.getElementById("metric-tokens");
    const metricCost = document.getElementById("metric-cost");
    const metricSteps = document.getElementById("metric-steps");
    const telemetryProgress = document.getElementById("telemetry-progress");
    
    // Database Elements
    const questionCountBadge = document.getElementById("question-count");
    const questionListContainer = document.getElementById("question-list-container");
    const dbSearchInput = document.getElementById("db-search");

    let allQuestions = [];

    // Load initial question bank
    loadQuestionBank();

    // Helper to get or create a step accordion card in real-time streaming
    function getOrCreateStepCard(stepNumber, stepsContainer) {
        let card = stepsContainer.querySelector(`.react-step-card[data-step="${stepNumber}"]`);
        if (!card) {
            card = document.createElement("div");
            card.classList.add("react-step-card");
            card.setAttribute("data-step", stepNumber);
            
            card.innerHTML = `
                <div class="step-header">
                    <div class="step-title-group">
                        <span class="step-number">${stepNumber}</span>
                        <h3 class="step-title-text">Bước ${stepNumber}: Đang suy nghĩ...</h3>
                    </div>
                    <span class="step-meta"></span>
                </div>
                <div class="step-body active">
                    <div class="thought-block hidden">
                        <div class="block-title">Thought (Suy nghĩ)</div>
                        <div class="block-content thought"></div>
                    </div>
                    <div class="action-block hidden">
                        <div class="block-title">Action (Gọi công cụ)</div>
                        <div class="block-content action"></div>
                    </div>
                    <div class="observation-block hidden">
                        <div class="block-title">Observation (Kết quả)</div>
                        <div class="block-content observation"></div>
                    </div>
                </div>
            `;
            
            // Toggle Expand handler
            const header = card.querySelector(".step-header");
            const body = card.querySelector(".step-body");
            header.addEventListener("click", () => {
                body.classList.toggle("active");
            });
            
            stepsContainer.appendChild(card);
            scrollChatToBottom();
        }
        return card;
    }

    // Event listener for chat form submission
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        // Clear input field
        chatInput.value = "";
        
        // Add User Message to UI
        addMessage(query, "user");
        
        // Show Typing Indicator
        const typingIndicator = addTypingIndicator();
        scrollChatToBottom();
        
        // Disable form and show spinner
        setSubmittingState(true);

        // Determine Mode
        const mode = document.querySelector('input[name="mode"]:checked').value;
        const provider = providerSelect.value;
        const model = modelSelect.value;

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: query,
                    mode: mode,
                    provider: provider,
                    model: model
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Remove typing indicator when streaming starts
            typingIndicator.remove();

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            let stepsContainer = null;
            let finalAnswerBubble = null;
            let finalAnswerText = "";
            let streamDone = false;

            while (true) {
                const { value, done } = await reader.read();
                if (done || streamDone) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop(); // Giữ lại dòng chưa hoàn chỉnh trong buffer

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        const dataStr = line.substring(6).trim();
                        if (!dataStr) continue;

                        try {
                            const event = JSON.parse(dataStr);

                            if (event.type === "error") {
                                addMessage(`❌ Lỗi từ hệ thống: ${event.message}`, "assistant");
                                continue;
                            }

                            if (event.type === "step_start") {
                                metricSteps.textContent = event.step;
                                if (mode === "react") {
                                    if (!stepsContainer) {
                                        stepsContainer = document.createElement("div");
                                        stepsContainer.classList.add("react-steps-container");
                                        chatMessages.appendChild(stepsContainer);
                                    }
                                    getOrCreateStepCard(event.step, stepsContainer);
                                }
                            }
                            else if (event.type === "thought_chunk") {
                                if (mode === "react" && stepsContainer) {
                                    const card = getOrCreateStepCard(event.step, stepsContainer);
                                    const block = card.querySelector(".thought-block");
                                    const div = card.querySelector(".thought");
                                    block.classList.remove("hidden");
                                    div.textContent += event.content;
                                    card.querySelector(".step-title-text").textContent = `Bước ${event.step}: Đang suy nghĩ...`;
                                }
                            }
                            else if (event.type === "action_chunk") {
                                if (mode === "react" && stepsContainer) {
                                    const card = getOrCreateStepCard(event.step, stepsContainer);
                                    const block = card.querySelector(".action-block");
                                    const div = card.querySelector(".action");
                                    block.classList.remove("hidden");
                                    div.textContent += event.content;
                                    card.querySelector(".step-title-text").textContent = `Bước ${event.step}: Chuẩn bị gọi công cụ...`;
                                }
                            }
                            else if (event.type === "tool_start") {
                                if (mode === "react" && stepsContainer) {
                                    const card = getOrCreateStepCard(event.step, stepsContainer);
                                    const block = card.querySelector(".action-block");
                                    const div = card.querySelector(".action");
                                    block.classList.remove("hidden");
                                    div.textContent = `${event.tool}(${event.args})`;
                                    card.querySelector(".step-title-text").textContent = `Bước ${event.step}: Chạy công cụ ${event.tool}...`;

                                    const obsBlock = card.querySelector(".observation-block");
                                    const obsDiv = card.querySelector(".observation");
                                    obsBlock.classList.remove("hidden");
                                    obsDiv.innerHTML = `<span class="tool-loading">Đang thực thi công cụ...</span>`;
                                }
                            }
                            else if (event.type === "tool_result") {
                                if (mode === "react" && stepsContainer) {
                                    const card = getOrCreateStepCard(event.step, stepsContainer);
                                    const obsBlock = card.querySelector(".observation-block");
                                    const obsDiv = card.querySelector(".observation");
                                    obsBlock.classList.remove("hidden");
                                    obsDiv.textContent = event.observation;
                                    card.querySelector(".step-title-text").textContent = `Bước ${event.step}: Đã gọi ${event.tool}`;
                                    
                                    if (event.metrics && event.metrics.latency_ms) {
                                        card.querySelector(".step-meta").textContent = `${(event.metrics.latency_ms / 1000).toFixed(2)}s`;
                                    }

                                    // Collapse previous step card bodies to clean up UI
                                    const allCards = stepsContainer.querySelectorAll(".react-step-card");
                                    allCards.forEach(c => {
                                        if (c !== card) {
                                            c.querySelector(".step-body").classList.remove("active");
                                        }
                                    });
                                }
                            }
                            else if (event.type === "warning") {
                                if (mode === "react" && stepsContainer) {
                                    const card = document.createElement("div");
                                    card.classList.add("react-step-card", "warning-card");
                                    card.innerHTML = `
                                        <div class="step-header warning-header" style="background: rgba(245, 158, 11, 0.1); border-left: 4px solid var(--accent-orange, #f59e0b);">
                                            <div class="step-title-group">
                                                <span class="step-number" style="background: var(--accent-orange, #f59e0b);">⚠️</span>
                                                <h3 style="color: var(--accent-orange, #f59e0b);">Nhắc nhở sửa đổi quy trình</h3>
                                            </div>
                                        </div>
                                        <div class="step-body active" style="border-left: 4px solid var(--accent-orange, #f59e0b); padding-top: 10px;">
                                            <div class="block-content observation" style="color: var(--text-primary); font-family: inherit;">${escapeHTML(event.message)}</div>
                                        </div>
                                    `;
                                    stepsContainer.appendChild(card);
                                    scrollChatToBottom();
                                }
                            }
                            else if (event.type === "final_answer_chunk") {
                                if (!finalAnswerBubble) {
                                    if (stepsContainer) {
                                        const allCards = stepsContainer.querySelectorAll(".react-step-card");
                                        allCards.forEach(c => {
                                            c.querySelector(".step-body").classList.remove("active");
                                        });
                                    }
                                    
                                    finalAnswerBubble = document.createElement("div");
                                    finalAnswerBubble.classList.add("message", "assistant");
                                    const contentDiv = document.createElement("div");
                                    contentDiv.classList.add("message-content");
                                    finalAnswerBubble.appendChild(contentDiv);
                                    chatMessages.appendChild(finalAnswerBubble);
                                }
                                
                                finalAnswerText += event.content;
                                
                                const formattedHTML = escapeHTML(finalAnswerText)
                                    .replace(/\n/g, "<br>")
                                    .replace(/\\\[([\s\S]+?)\\\]/g, '<div class="math-block">$$1$</div>')
                                    .replace(/\\\(([\s\S]+?)\\\)/g, '<span class="math-inline">$$1$</span>')
                                    .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
                                    .replace(/\*([\s\S]+?)\*/g, '<em>$1</em>')
                                    .replace(/`([\s\S]+?)`/g, '<code class="inline-code">$1</code>');
                                    
                                finalAnswerBubble.querySelector(".message-content").innerHTML = formattedHTML;
                                scrollChatToBottom();
                            }
                            else if (event.type === "done") {
                                if (event.response) {
                                    if (!finalAnswerBubble) {
                                        finalAnswerBubble = document.createElement("div");
                                        finalAnswerBubble.classList.add("message", "assistant");
                                        const contentDiv = document.createElement("div");
                                        contentDiv.classList.add("message-content");
                                        finalAnswerBubble.appendChild(contentDiv);
                                        chatMessages.appendChild(finalAnswerBubble);
                                    }
                                    
                                    const formattedHTML = escapeHTML(event.response)
                                        .replace(/\n/g, "<br>")
                                        .replace(/\\\[([\s\S]+?)\\\]/g, '<div class="math-block">$$1$</div>')
                                        .replace(/\\\(([\s\S]+?)\\\)/g, '<span class="math-inline">$$1$</span>')
                                        .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
                                        .replace(/\*([\s\S]+?)\*/g, '<em>$1</em>')
                                        .replace(/`([\s\S]+?)`/g, '<code class="inline-code">$1</code>');
                                        
                                    finalAnswerBubble.querySelector(".message-content").innerHTML = formattedHTML;
                                }
                                
                                if (event.telemetry) {
                                    updateTelemetry(event.telemetry);
                                }
                                
                                loadQuestionBank(true); // isPostRun=true để detect câu mới
                                
                                // Tắt spinner ngay lập tức và thoát khỏi vòng lặp stream
                                streamDone = true;
                                setSubmittingState(false);
                                scrollChatToBottom();
                                break;
                            }
                        } catch (parseErr) {
                            console.error("Error parsing SSE JSON chunk:", parseErr, dataStr);
                        }
                    }
                }
                
                if (streamDone) break;
            }
        } catch (error) {
            console.error("Error sending message:", error);
            typingIndicator.remove();
            addMessage(`❌ Lỗi kết nối đến máy chủ: ${error.message}`, "assistant");
        } finally {
            setSubmittingState(false);
            scrollChatToBottom();
        }
    });

    // Clear chat button handler
    btnClearChat.addEventListener("click", () => {
        chatMessages.innerHTML = `
            <div class="message system-message">
                <div class="message-content">
                    <strong>Chào mừng bạn đến với AI Trợ Lý Giáo Dục!</strong><br>
                    Hệ thống hỗ trợ tra cứu chương trình của Bộ Giáo dục, truy vấn và tự động cập nhật ngân hàng câu hỏi.<br><br>
                    <em>Gợi ý yêu cầu nhanh:</em>
                    <div class="prompt-chips">
                        <button class="prompt-chip" onclick="usePrompt('Thiết kế đề kiểm tra Toán lớp 12 gồm 3 câu hỏi trắc nghiệm chủ đề \\'Hàm số lũy thừa\\' (1 Dễ, 2 Trung bình). Ưu tiên lấy từ ngân hàng, nếu thiếu tự sinh mới và lưu.')">Toán 12 - Hàm số lũy thừa</button>
                        <button class="prompt-chip" onclick="usePrompt('Tạo đề kiểm tra Vật lý lớp 12 gồm 2 câu trắc nghiệm chủ đề \\'Dao động cơ\\' (1 câu Dễ, 1 câu Trung bình). Hãy lưu câu mới sinh vào ngân hàng.')">Lý 12 - Dao động cơ</button>
                    </div>
                </div>
            </div>
        `;
        resetTelemetry();
    });

    // Database Search input filter
    dbSearchInput.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase().trim();
        filterQuestions(query);
    });

    // Function to set submit button state
    function setSubmittingState(isSubmitting) {
        if (isSubmitting) {
            btnSubmitChat.disabled = true;
            chatInput.disabled = true;
            btnText.classList.add("hidden");
            btnSpinner.classList.remove("hidden");
        } else {
            btnSubmitChat.disabled = false;
            chatInput.disabled = false;
            btnText.classList.remove("hidden");
            btnSpinner.classList.add("hidden");
        }
    }

    // Function to add a normal message bubble
    function addMessage(text, sender) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", sender);
        
        const contentDiv = document.createElement("div");
        contentDiv.classList.add("message-content");
        
        // Simple markdown replacement for LaTeX math blocks
        let htmlContent = escapeHTML(text)
            .replace(/\n/g, "<br>")
            .replace(/\\\[([\s\S]+?)\\\]/g, '<div class="math-block">$$1$</div>')
            .replace(/\\\(([\s\S]+?)\\\)/g, '<span class="math-inline">$$1$</span>')
            .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([\s\S]+?)\*/g, '<em>$1</em>')
            .replace(/`([\s\S]+?)`/g, '<code class="inline-code">$1</code>');
            
        contentDiv.innerHTML = htmlContent;
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        scrollChatToBottom();
    }

    // Function to add typing indicator bubble
    function addTypingIndicator() {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", "assistant", "typing-indicator-msg");
        
        const contentDiv = document.createElement("div");
        contentDiv.classList.add("message-content", "typing-indicator");
        contentDiv.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
        
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        return messageDiv;
    }

    // Function to add ReAct Step Expansion Cards
    function addReActSteps(steps) {
        const stepsContainer = document.createElement("div");
        stepsContainer.classList.add("react-steps-container");

        steps.forEach((step) => {
            const stepCard = document.createElement("div");
            stepCard.classList.add("react-step-card");

            const isWarning = step.action && step.action.includes("Hệ thống");
            const stepTitle = isWarning ? `Nhắc nhở sửa đổi quy trình` : `Bước ${step.step}: ${step.action ? step.action.split("(")[0] : "Suy nghĩ"}`;
            const stepTime = step.metrics ? `${(step.metrics.latency_ms / 1000).toFixed(2)}s` : "";

            stepCard.innerHTML = `
                <div class="step-header">
                    <div class="step-title-group">
                        <span class="step-number">${step.step}</span>
                        <h3>${stepTitle}</h3>
                    </div>
                    <span class="step-meta">${stepTime}</span>
                </div>
                <div class="step-body">
                    ${step.thought ? `
                        <div>
                            <div class="block-title">Thought (Suy nghĩ)</div>
                            <div class="block-content thought">${escapeHTML(step.thought)}</div>
                        </div>
                    ` : ""}
                    ${step.action ? `
                        <div>
                            <div class="block-title">Action (Gọi công cụ)</div>
                            <div class="block-content action">${escapeHTML(step.action)}</div>
                        </div>
                    ` : ""}
                    ${step.observation ? `
                        <div>
                            <div class="block-title">Observation (Kết quả)</div>
                            <div class="block-content observation">${escapeHTML(step.observation)}</div>
                        </div>
                    ` : ""}
                </div>
            `;

            // Toggle Expand handler
            const header = stepCard.querySelector(".step-header");
            const body = stepCard.querySelector(".step-body");
            header.addEventListener("click", () => {
                body.classList.toggle("active");
            });

            // Expand the last few steps by default
            if (step.step === steps.length || isWarning) {
                body.classList.add("active");
            }

            stepsContainer.appendChild(stepCard);
        });

        chatMessages.appendChild(stepsContainer);
        scrollChatToBottom();
    }

    // Function to load questions from database
    async function loadQuestionBank(isPostRun = false) {
        try {
            const prevCount = allQuestions.length;
            const response = await fetch("/api/questions");
            if (!response.ok) throw new Error("Could not load questions.");
            
            allQuestions = await response.json();
            const newCount = allQuestions.length;
            questionCountBadge.textContent = `${allQuestions.length} câu`;
            
            // Nếu có câu mới được thêm vào sau khi agent chạy
            if (isPostRun && newCount > prevCount) {
                const added = newCount - prevCount;
                // Animate badge
                questionCountBadge.classList.add("badge-pulse");
                setTimeout(() => questionCountBadge.classList.remove("badge-pulse"), 2000);
                
                // Hiển thị thông báo câu mới
                showSavedNotification(added);
                
                // Render với highlight câu mới
                renderQuestions(allQuestions, prevCount);
            } else {
                renderQuestions(allQuestions);
            }
        } catch (error) {
            console.error("Error loading question bank:", error);
            questionListContainer.innerHTML = `<div class="error-msg" style="color: red; font-size: 12px; text-align: center;">❌ Lỗi kết nối DB</div>`;
        }
    }

    // Hiển thị thông báo câu hỏi mới được lưu
    function showSavedNotification(count) {
        const notif = document.createElement("div");
        notif.style.cssText = `
            position: fixed; bottom: 24px; right: 24px; z-index: 9999;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white; padding: 12px 20px; border-radius: 12px;
            font-size: 14px; font-weight: 600; font-family: 'Outfit', sans-serif;
            box-shadow: 0 8px 30px rgba(16, 185, 129, 0.4);
            animation: slideInUp 0.4s ease;
            display: flex; align-items: center; gap: 8px;
        `;
        notif.innerHTML = `✅ Đã lưu <strong>${count} câu hỏi mới</strong> vào ngân hàng!`;
        document.body.appendChild(notif);
        setTimeout(() => { notif.style.opacity = "0"; notif.style.transition = "opacity 0.5s"; }, 2500);
        setTimeout(() => notif.remove(), 3100);
    }


    // Render question bank in sidebar list
    function renderQuestions(questions, prevCount = null) {
        if (questions.length === 0) {
            questionListContainer.innerHTML = `<div style="text-align: center; color: var(--text-secondary); font-size: 12px; margin-top: 20px;">Ngân hàng trống</div>`;
            return;
        }

        questionListContainer.innerHTML = "";
        questions.forEach((q, index) => {
            const card = document.createElement("div");
            card.classList.add("question-card");
            
            // Highlight mới nếu index >= prevCount (câu hỏi mới)
            const isNew = prevCount !== null && index >= prevCount;
            if (isNew) {
                card.style.cssText = `
                    border: 1px solid rgba(16, 185, 129, 0.5) !important;
                    background: rgba(16, 185, 129, 0.08) !important;
                    animation: fadeInDown 0.5s ease ${(index - prevCount) * 0.1}s both;
                `;
            }

            const diffClass = `diff-${q.difficulty.toLowerCase()}`;
            card.innerHTML = `
                <div class="q-meta">
                    <span class="q-badge id">${q.id}</span>
                    ${isNew ? '<span style="background: rgba(16,185,129,0.2); color: #10b981; padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 700;">✨ MỚI</span>' : ''}
                    <span class="q-badge ${diffClass}">${q.difficulty}</span>
                    <span class="q-badge id" style="background-color: rgba(139, 92, 246, 0.1); color: var(--accent-purple);">${q.topic}</span>
                </div>
                <div class="q-text">${escapeHTML(q.question_text)}</div>
            `;
            questionListContainer.appendChild(card);
        });
    }

    // Filter questions list
    function filterQuestions(searchQuery) {
        if (!searchQuery) {
            renderQuestions(allQuestions);
            return;
        }
        const filtered = allQuestions.filter((q) => 
            q.question_text.toLowerCase().includes(searchQuery) ||
            q.topic.toLowerCase().includes(searchQuery) ||
            q.id.toLowerCase().includes(searchQuery)
        );
        renderQuestions(filtered);
    }

    // Update telemetry counters
    function updateTelemetry(metrics) {
        if (!metrics) return;
        metricLatency.textContent = `${metrics.latency_ms.toLocaleString()} ms (${(metrics.latency_ms/1000).toFixed(2)}s)`;
        metricTokens.textContent = `${metrics.total_tokens.toLocaleString()} (P: ${metrics.prompt_tokens} / C: ${metrics.completion_tokens})`;
        metricCost.textContent = `$${metrics.cost_estimate.toFixed(5)}`;
        metricSteps.textContent = metrics.steps;
        
        // Update visual progress bar (e.g. max limit 7 steps = 100%)
        const pct = Math.min((metrics.steps / 7) * 100, 100);
        telemetryProgress.style.width = `${pct}%`;
    }

    // Reset telemetry counters to 0
    function resetTelemetry() {
        metricLatency.textContent = "0 ms";
        metricTokens.textContent = "0";
        metricCost.textContent = "$0.00000";
        metricSteps.textContent = "0";
        telemetryProgress.style.width = "0%";
    }

    // Helper functions
    function scrollChatToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHTML(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Global utility to insert prompt chip directly to input area
    window.usePrompt = function(promptText) {
        chatInput.value = promptText;
        chatInput.focus();
    };
});
