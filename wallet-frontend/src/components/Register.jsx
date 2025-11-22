import React, { useState } from "react";
import api from "../api/axiosConfig";

export default function Register() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [mobile, setMobile] = useState("");
  const [currencies, setCurrencies] = useState([]);
  const [currency, setCurrency] = useState("KES");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState(""); // success or error

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    if (password !== confirmPassword) {
      setMessage("❌ Passwords do not match!");
      setMessageType("error");
      return;
    }

    try {
      const response = await api.post("register/", {
        first_name: firstName,
        last_name: lastName,
        username,
        email,
        mobile,
        password,
        confirm_password: confirmPassword,
        currency,
      });

      setMessage(response.data?.message || "✅ Account created successfully!");
      setMessageType("success");

      // Clear input fields
      setFirstName("");
      setLastName("");
      setUsername("");
      setEmail("");
      setMobile("");
      setPassword("");
      setConfirmPassword("");

      // Auto-hide message after 4 seconds
      setTimeout(() => setMessage(""), 4000);
    } catch (error) {
      const errorMsg =
        error.response?.data?.error ||
        error.response?.data?.message ||
        "❌ Registration failed. Please try again.";
      setMessage(errorMsg);
      setMessageType("error");
    }
  };

  React.useEffect(() => {
    // fetch supported currencies (no auth required)
    api
      .get("currencies/")
      .then((res) => {
        const cs = res.data.currencies || [];
        setCurrencies(cs);
        if (cs.length) setCurrency(cs[0].code || "KES");
      })
      .catch(() => {
        // fallback
        setCurrencies([{ code: "KES", name: "Kenyan Shilling" }]);
      });
  }, []);

  return (
    <div style={{ maxWidth: 400, margin: "50px auto", textAlign: "center" }}>
      <h2>Create Account</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="First Name"
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
          required
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <input
          type="text"
          placeholder="Last Name"
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
          required
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <input
          type="email"
          placeholder="Email (optional)"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <input
          type="text"
          placeholder="Mobile Number"
          value={mobile}
          onChange={(e) => setMobile(e.target.value)}
          required
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <input
          type="password"
          placeholder="Confirm Password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
          style={{ width: "100%", padding: "10px", margin: "8px 0" }}
        />
        <div style={{ margin: "8px 0" }}>
          <label style={{ display: "block", marginBottom: 6 }}>Wallet Currency</label>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            required
            style={{ width: "100%", padding: "10px" }}
          >
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>{c.code} - {c.name}</option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          style={{
            width: "100%",
            padding: "10px",
            marginTop: "10px",
            backgroundColor: "#007bff",
            color: "white",
            border: "none",
            cursor: "pointer",
          }}
        >
          Register
        </button>
      </form>

      {message && (
        <p
          style={{
            marginTop: "15px",
            color: messageType === "success" ? "green" : "red",
            fontWeight: "bold",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
}
