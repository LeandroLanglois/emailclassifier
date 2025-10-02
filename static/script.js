document.getElementById("classifyBtn").addEventListener("click", async () => {
    const emailText = document.getElementById("emailText").value;
    const fileUpload = document.getElementById("fileUpload").files[0];

    const loadingDiv = document.getElementById("loading");
    const errorDiv = document.getElementById("error");
    const resultsDiv = document.getElementById("results");

    loadingDiv.classList.remove("hidden");
    errorDiv.classList.add("hidden");
    resultsDiv.classList.add("hidden");

    let textToSend = emailText;

    if (fileUpload) {
        if (fileUpload.type === "text/plain") {
            textToSend = await fileUpload.text();
        } else if (fileUpload.type === "application/pdf") {
            errorDiv.textContent = "📄 PDFs ainda não são suportados neste exemplo.";
            errorDiv.classList.remove("hidden");
            loadingDiv.classList.add("hidden");
            return;
        }
    }

    try {
        const response = await fetch("/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: textToSend })
        });

        const data = await response.json();
        loadingDiv.classList.add("hidden");

        if (data.error) {
            errorDiv.textContent = data.error;
            errorDiv.classList.remove("hidden");
        } else {
            document.getElementById("category").textContent = data.classification.category;
            document.getElementById("response").textContent = data.classification.suggested_response;
            resultsDiv.classList.remove("hidden");
        }
    } catch (err) {
        loadingDiv.classList.add("hidden");
        errorDiv.textContent = "Erro de conexão com o servidor.";
        errorDiv.classList.remove("hidden");
    }
});
