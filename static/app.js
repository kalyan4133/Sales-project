const textEl = document.getElementById("text");
const fileEl = document.getElementById("file");
const companyEl = document.getElementById("company");
const msgEl = document.getElementById("msg");

const submitBtn = document.getElementById("submitBtn");
const submitText = document.getElementById("submitText");
const submitSpinner = document.getElementById("submitSpinner");
const clearBtn = document.getElementById("clearBtn");

function setMsg(s, type = "info") {
  msgEl.className = `msg ${type}`;
  msgEl.textContent = s || "";
}

function withTimeout(ms) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), ms);
  return { controller, id };
}

clearBtn?.addEventListener("click", () => {
  textEl.value = "";
  companyEl.value = "";
  fileEl.value = "";
  setMsg("");
});

submitBtn?.addEventListener("click", async () => {
  const text = (textEl.value || "").trim();
  const file = fileEl.files && fileEl.files[0];
  const company_name = (companyEl.value || "").trim();

  if (!text && !file) {
    setMsg("Please paste text or upload a file.", "error");
    return;
  }

  setMsg("Submitting to agent…", "info");
  submitBtn.disabled = true;
  if (submitText) submitText.textContent = "Submitting";
  if (submitSpinner) submitSpinner.classList.remove("hidden");

  const { controller, id } = withTimeout(60000); // 60s timeout

  try {
    let result;

    if (file) {
      const fd = new FormData();
      fd.append("file", fileEl.files[0]);

      const res = await fetch("/analyze/file", {
        method: "POST",
        body: fd,
        signal: controller.signal
      });

      const contentType = res.headers.get("content-type") || "";
      const body = contentType.includes("application/json") ? await res.json() : await res.text();

      if (!res.ok) throw new Error(typeof body === "string" ? body : (body.detail || JSON.stringify(body)));

      result = body;

      // inject company name if user entered it
      if (company_name) {
        result.customer = result.customer || {};
        result.customer.company_name = company_name;
      }
    } else {
      const res = await fetch("/analyze/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          structured: company_name ? { company_name } : {}
        }),
        signal: controller.signal
      });

      const contentType = res.headers.get("content-type") || "";
      const body = contentType.includes("application/json") ? await res.json() : await res.text();

      if (!res.ok) throw new Error(typeof body === "string" ? body : (body.detail || JSON.stringify(body)));

      result = body;
    }

    // Validate response before redirect
    if (!result || typeof result !== "object") {
      throw new Error("Agent returned empty response.");
    }

    sessionStorage.setItem("analysisResult", JSON.stringify(result));
    setMsg("Success ✅ Redirecting…", "ok");

    // redirect
    window.location.assign("/output");
  } catch (e) {
    const msg = (e?.name === "AbortError")
      ? "Request timed out (60s). Gemini may be slow. Try again or shorten the input."
      : `Error: ${e.message || e}`;

    setMsg(msg, "error");
    console.error(e);
  } finally {
    clearTimeout(id);
    submitBtn.disabled = false;
    if (submitText) submitText.textContent = "Submit ➜";
    if (submitSpinner) submitSpinner.classList.add("hidden");
  }
});

async function openProductView(productName) {
  const res = await fetch("/quote/product/view", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ product_name: productName })
  });

  const data = await res.json();

  document.getElementById("pm_name").textContent = data.product_name;
  document.getElementById("pm_id").textContent = data.product_id;

  document.getElementById("pm_pros").innerHTML = (data.pros || []).map(x => `<span class="chip">${x}</span>`).join("");
  document.getElementById("pm_cons").innerHTML = (data.cons || []).map(x => `<span class="chip">${x}</span>`).join("");

  document.getElementById("pm_reason").textContent = data.reason_to_buy || "";

  document.getElementById("productModal").classList.remove("hidden");
}

function closeProductView() {
  document.getElementById("productModal").classList.add("hidden");
}
