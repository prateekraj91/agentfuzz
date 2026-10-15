const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendButton = document.getElementById("send-button");

const chatMessages = document.getElementById("chat-messages");
const calendarPanel = document.getElementById("calendar-panel");
const remindersPanel = document.getElementById("reminders-panel");
const actionLog = document.getElementById("action-log");
const connectionStatus = document.getElementById("connection-status");

function addMessage(text, sender, isError = false) {
    const message = document.createElement("div");
    message.className = `message ${sender}${isError ? " error" : ""}`;
    message.textContent = text;
    chatMessages.appendChild(message);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addLog(title, details) {
    const entry = document.createElement("div");
    entry.className = "log-entry";

    const heading = document.createElement("strong");
    heading.textContent = title;

    const body = document.createElement("div");
    body.textContent = typeof details === "string"
        ? details
        : JSON.stringify(details, null, 2);

    entry.append(heading, body);
    actionLog.prepend(entry);
}

function showMessageConfirmation(pending) {
    const container = document.createElement("div");
    container.className = "message assistant";

    const prompt = document.createElement("p");
    prompt.textContent =
        `Send this message to ${pending.recipient}?`;

    const content = document.createElement("p");
    content.textContent = pending.message;

    const confirmButton = document.createElement("button");
    confirmButton.textContent = "Confirm";
    confirmButton.type = "button";

    const cancelButton = document.createElement("button");
    cancelButton.textContent = "Cancel";
    cancelButton.type = "button";

    const buttons = document.createElement("div");
    buttons.append(confirmButton, cancelButton);

    container.append(prompt, content, buttons);
    chatMessages.appendChild(container);

    async function submitConfirmation(confirmed) {
        confirmButton.disabled = true;
        cancelButton.disabled = true;

        try {
            const response = await fetch("/confirm", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ confirmed }),
            });

            const result = await response.json();

            if (!response.ok || result.status === "error") {
                throw new Error(
                    result.message || "Confirmation failed."
                );
            }

            container.remove();

            addMessage(
                confirmed
                    ? "Message sent successfully."
                    : "Message cancelled. Nothing was sent.",
                "assistant"
            );

            addLog("Message confirmation", result);
            await refreshState();
        } catch (error) {
            confirmButton.disabled = false;
            cancelButton.disabled = false;

            addMessage(
                `Confirmation failed: ${error.message}`,
                "assistant",
                true
            );
        } 
    }

    confirmButton.addEventListener("click", () => {
        submitConfirmation(true);
    });

    cancelButton.addEventListener("click", () => {
        submitConfirmation(false);
    });

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatTime(time) {
    const [hours, minutes] = time.split(":").map(Number);
    const suffix = hours >= 12 ? "PM" : "AM";
    const displayHour = hours % 12 || 12;
    return `${displayHour}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

async function refreshState() {
    const response = await fetch("/state");

    if (!response.ok) {
        throw new Error("Could not load application state.");
    }

    const state = await response.json();

    calendarPanel.replaceChildren();

    if (!state.calendar || state.calendar.length === 0) {
        calendarPanel.textContent = "No calendar events.";
    } else {
        for (const meeting of state.calendar) {
            const card = document.createElement("div");
            card.className = "calendar-item";

            const title = document.createElement("p");
            title.className = "item-title";
            title.textContent = meeting.title;

            const detail = document.createElement("p");
            detail.className = "item-detail";
            detail.textContent =
                `${formatTime(meeting.time)} · ${meeting.date}`;

            card.append(title, detail);
            calendarPanel.appendChild(card);
        }
    }

    remindersPanel.replaceChildren();

    if (!state.reminders || state.reminders.length === 0) {
        remindersPanel.textContent = "No reminders yet.";
    } else {
        for (const reminder of state.reminders) {
            const card = document.createElement("div");
            card.className = "reminder-item";

            const title = document.createElement("p");
            title.className = "item-title";
            title.textContent = reminder.title;

            const detail = document.createElement("p");
            detail.className = "item-detail";
            detail.textContent = formatTime(reminder.time);

            card.append(title, detail);
            remindersPanel.appendChild(card);
        }
    }
}

async function checkPendingMessage() {
    try {
        const response = await fetch("/pending");

        if (!response.ok) {
            return;
        }

        const data = await response.json();

        if (data.pending) {
            showMessageConfirmation(data.pending);
        }
    } catch (error) {
        // Not critical for startup; ignore silently.
    }
}

async function checkConnection() {
    try {
        const response = await fetch("/health");

        if (!response.ok) {
            throw new Error("API unavailable");
        }

        connectionStatus.textContent = "API connected";
        connectionStatus.style.color = "#75d6a0";
        await refreshState();
        await checkPendingMessage();
    } catch (error) {
        connectionStatus.textContent = "API disconnected";
        connectionStatus.style.color = "#ff8080";
        addLog("Connection error", error.message);
    }
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = chatInput.value.trim();

    if (!message) {
        return;
    }

    addMessage(message, "user");
    chatInput.value = "";
    sendButton.disabled = true;
    sendButton.textContent = "Working...";

    try {
        addLog("User request", message);

        const response = await fetch("/run", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message }),
        });

        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }

        const result = await response.json();

        if (result.pending_confirmation) {
            showMessageConfirmation(result.pending_confirmation);
        }

        if (!result.pending_confirmation) {
            addMessage(
                result.reply || "The agent returned no final response.",
                "assistant"
            );
        }

        if (Array.isArray(result.trace)) {
            for (const item of result.trace) {
                addLog(`Tool: ${item.tool}`, {
                    step: item.step,
                    arguments: item.arguments,
                    result: item.result,
                });
            }
        }

        await refreshState();
    } catch (error) {
        addMessage(`Request failed: ${error.message}`, "assistant", true);
        addLog("Request error", error.message);
    } finally {
        sendButton.disabled = false;
        sendButton.textContent = "Send";
        chatInput.focus();
    }
});

checkConnection();