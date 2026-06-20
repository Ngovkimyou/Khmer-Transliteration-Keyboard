const input = document.querySelector("#romanInput");
const clearButton = document.querySelector("#clearButton");
const collectButton = document.querySelector("#collectButton");
const normalizedText = document.querySelector("#normalizedText");
const suggestionsEl = document.querySelector("#suggestions");
const emptyState = document.querySelector("#emptyState");
const countText = document.querySelector("#countText");
const outputText = document.querySelector("#outputText");
const modelStatus = document.querySelector("#modelStatus");
const collectStatus = document.querySelector("#collectStatus");

let activeRequest = 0;

const KHMER_DIGITS_BY_CODE = {
    Digit0: "០",
    Digit1: "១",
    Digit2: "២",
    Digit3: "៣",
    Digit4: "៤",
    Digit5: "៥",
    Digit6: "៦",
    Digit7: "៧",
    Digit8: "៨",
    Digit9: "៩",
    Numpad0: "០",
    Numpad1: "១",
    Numpad2: "២",
    Numpad3: "៣",
    Numpad4: "៤",
    Numpad5: "៥",
    Numpad6: "៦",
    Numpad7: "៧",
    Numpad8: "៨",
    Numpad9: "៩",
};

const KHMER_SHIFT_TOP_ROW_BY_CODE = {
    Digit1: "!",
    Digit2: "ៗ",
    Digit3: "\"",
    Digit4: "៛",
    Digit5: "%",
    Digit6: "៍",
    Digit7: "័",
    Digit8: "៏",
    Digit9: "(",
    Digit0: ")",
    Minus: "=",
    Equal: "៎",
};

const KHMER_DIRECT_KEYS_BY_CODE = {
    Period: "។",
    NumpadDecimal: "។",
};

function insertTextAtCursor(element, text) {
    const start = element.selectionStart ?? element.value.length;
    const end = element.selectionEnd ?? element.value.length;
    element.value = `${element.value.slice(0, start)}${text}${element.value.slice(end)}`;
    const nextPosition = start + text.length;
    element.setSelectionRange(nextPosition, nextPosition);
}

function getKhmerKeyboardCharacter(event) {
    if (event.ctrlKey || event.metaKey || event.altKey) {
        return null;
    }

    if (event.shiftKey && KHMER_SHIFT_TOP_ROW_BY_CODE[event.code]) {
        return KHMER_SHIFT_TOP_ROW_BY_CODE[event.code];
    }

    if (!event.shiftKey && KHMER_DIGITS_BY_CODE[event.code]) {
        return KHMER_DIGITS_BY_CODE[event.code];
    }

    if (!event.shiftKey && KHMER_DIRECT_KEYS_BY_CODE[event.code]) {
        return KHMER_DIRECT_KEYS_BY_CODE[event.code];
    }

    return null;
}

function handleKhmerKeyboardInput(event) {
    const khmerCharacter = getKhmerKeyboardCharacter(event);

    if (!khmerCharacter) {
        return;
    }

    event.preventDefault();

    if (event.currentTarget === outputText) {
        insertTextAtCursor(outputText, khmerCharacter);
        return;
    }

    insertTextAtCursor(outputText, khmerCharacter);
    input.value = "";
    renderSuggestions({ normalized: "", suggestions: [] });
}

function sourceLabel(source) {
    if (source === "dictionary_exact") {
        return "exact";
    }

    if (source === "dictionary_completion") {
        return "completion";
    }

    if (source === "dictionary_compound") {
        return "compound";
    }

    if (source === "dictionary_fuzzy") {
        return "fuzzy";
    }

    if (source.startsWith("rule_")) {
        return "rule";
    }

    if (source.startsWith("direct_")) {
        return "direct";
    }

    return source;
}

function sourceClass(source) {
    if (source === "dictionary_exact") {
        return "exact";
    }

    if (source === "dictionary_completion") {
        return "completion";
    }

    if (source === "dictionary_compound") {
        return "completion";
    }

    if (source === "dictionary_fuzzy") {
        return "completion";
    }

    if (source.startsWith("rule_")) {
        return "rule";
    }

    if (source.startsWith("direct_")) {
        return "direct";
    }

    return "";
}

function formatScore(value) {
    if (value === undefined || value === null || value === "") {
        return null;
    }

    return Number(value).toFixed(4);
}

function renderSuggestions(data) {
    const suggestions = data.suggestions || [];
    normalizedText.textContent = data.normalized || "empty";
    countText.textContent = `${suggestions.length} result${suggestions.length === 1 ? "" : "s"}`;
    suggestionsEl.innerHTML = "";
    emptyState.classList.toggle("visible", suggestions.length === 0);

    for (const suggestion of suggestions) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "suggestion";
        button.setAttribute("aria-label", `Insert ${suggestion.khmer}`);

        const mlScore = formatScore(suggestion.ml_score);
        const manualScore = formatScore(suggestion.score);
        const rankScore = formatScore(suggestion.rank_score);
        const datasetScore = formatScore(suggestion.dataset_match_score);
        const source = sourceLabel(suggestion.source);
        const sourceCss = sourceClass(suggestion.source);

        button.innerHTML = `
            <span class="khmer">${suggestion.khmer}</span>
            <span class="meta">
                <span class="pill ${sourceCss}">${source}</span>
                ${suggestion.manual_label !== undefined ? `<span class="pill">label ${suggestion.manual_label}</span>` : ""}
                ${rankScore ? `<span class="pill">rank ${rankScore}</span>` : ""}
                ${suggestion.rank_reason ? `<span class="pill">${suggestion.rank_reason}</span>` : ""}
                ${datasetScore ? `<span class="pill">dataset ${datasetScore}${suggestion.dataset_romanized ? ` ${suggestion.dataset_romanized}` : ""}</span>` : ""}
                ${mlScore ? `<span class="pill">ML ${mlScore}</span>` : ""}
                ${manualScore ? `<span class="pill">manual ${manualScore}</span>` : ""}
            </span>
        `;

        button.addEventListener("click", () => {
            outputText.value += suggestion.khmer;
            input.value = "";
            renderSuggestions({ normalized: "", suggestions: [] });
            input.focus();
        });

        suggestionsEl.appendChild(button);
    }
}

async function fetchSuggestions() {
    const query = input.value.trim();
    const requestId = ++activeRequest;

    if (!query) {
        renderSuggestions({ normalized: "", suggestions: [] });
        return;
    }

    modelStatus.textContent = "Ranking...";

    try {
        const allowVowels = outputText.value.length > 0;
        const response = await fetch(
            `/api/suggest?q=${encodeURIComponent(query)}&allow_vowels=${allowVowels}`
        );

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        const data = await response.json();

        if (requestId !== activeRequest) {
            return;
        }

        renderSuggestions(data);
        modelStatus.textContent = "Model ready";
    } catch (error) {
        if (requestId !== activeRequest) {
            return;
        }

        modelStatus.textContent = "API error";
        suggestionsEl.innerHTML = "";
        emptyState.textContent = "Could not load suggestions. Check the server console.";
        emptyState.classList.add("visible");
    }
}

input.addEventListener("input", fetchSuggestions);
input.addEventListener("keydown", handleKhmerKeyboardInput);
outputText.addEventListener("keydown", handleKhmerKeyboardInput);

clearButton.addEventListener("click", () => {
    input.value = "";
    renderSuggestions({ normalized: "", suggestions: [] });
    collectStatus.textContent = "";
    input.focus();
});

collectButton.addEventListener("click", async () => {
    const query = input.value.trim();

    if (!query) {
        collectStatus.textContent = "Type a word before confirming.";
        input.focus();
        return;
    }

    collectStatus.textContent = "Sending candidates to review CSV...";

    try {
        const response = await fetch(`/api/collect?q=${encodeURIComponent(query)}`, {
            method: "POST",
        });

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        const data = await response.json();
        collectStatus.textContent = `${data.message} Open data/ranking_training_examples.csv to label them.`;
    } catch (error) {
        collectStatus.textContent = "Could not save candidates. Check the server console.";
    }
});

renderSuggestions({ normalized: "", suggestions: [] });
