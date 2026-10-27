const loginForm = document.getElementById("loginForm");
const message = document.getElementById("message");
const loginButton = document.getElementById("loginButton");

// Intentionally nonexistent API endpoint
const API_URL = "https://api.example.invalid/login";

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  message.textContent = "";
  message.className = "";
  loginButton.disabled = true;

  console.log("[Login] Sending request to:", API_URL);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value
      })
    });

    if (!response.ok) {
      throw new Error(`API request failed: HTTP ${response.status}`);
    }

    console.log("[Login] Login request succeeded.");
  } catch (error) {
    console.error("[Login] API ERROR:", error);

    message.textContent =
      "Unable to connect to the login server.";
    message.className = "error";
  } finally {
    loginButton.disabled = false;
  }
});
