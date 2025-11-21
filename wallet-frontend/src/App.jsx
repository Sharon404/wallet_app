import React, { useEffect} from "react";
import { BrowserRouter as Router, Routes, Route, Link } from "react-router-dom";
import Register from "./components/Register";
import Login from "./components/login";
import VerifyOtp from "./components/verifyotp";
import Wallet from "./components/wallet";

function App() {
  useEffect(() => {
    // Clear tokens on logout (tab close, visibility change)
    const handleLogout = () => {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    };

    // Inactivity logout after 30 minutes
    let timeout;
    const resetTimer = () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login"; // force logout + redirect
      }, 30 * 60 * 1000); // 30 minutes
    };

    // Attach events
    window.addEventListener("mousemove", resetTimer);
    window.addEventListener("keypress", resetTimer);
    window.addEventListener("beforeunload", handleLogout);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) handleLogout();
    });

    // Start timer
    resetTimer();

    // Cleanup
    return () => {
      window.removeEventListener("mousemove", resetTimer);
      window.removeEventListener("keypress", resetTimer);
      window.removeEventListener("beforeunload", handleLogout);
      document.removeEventListener("visibilitychange", () => {
        if (document.hidden) handleLogout();
      });
      clearTimeout(timeout);
    };
  }, []);

  // Main App component with routing
  return (
    <Router>
      <div style={{ textAlign: "center", marginTop: "20px" }}>
        <h1>Wallet System</h1>

        {/* Simple navigation for testing */}
        <nav style={{ marginBottom: "20px" }}>
          <Link to="/register" style={{ margin: "0 10px" }}>Register</Link>
          <Link to="/login" style={{ margin: "0 10px" }}>Login</Link>
          <Link to="/verify-otp" style={{ margin: "0 10px" }}>Verify OTP</Link>
          <Link to="/wallet" style={{ margin: "0 10px" }}>Wallet</Link>
        </nav>

        {/* Define routes (pages) */}
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/login" element={<Login />} />
          <Route path="/verify-otp" element={<VerifyOtp />} />
          <Route path="/wallet" element={<Wallet />} />
        </Routes>
      </div>
    </Router>
  );
}



export default App;