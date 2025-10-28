import React, { useEffect, useState } from "react";
import axios from "../api/axiosConfig";
import { useNavigate } from "react-router-dom";

axios.defaults.baseURL = "http://127.0.0.1:8000/api";

const WalletHome = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0.0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      navigate("/login");
      return;
    }

    axios
      .get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        setUser(res.data);
        setBalance(parseFloat(res.data.balance) || 0.0);
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem("token");
        navigate("/login");
      });
  }, [navigate]);

  // ✅ Move all handlers inside the component

  const handleDeposit = async () => {
    const amount = prompt("Enter deposit amount (KES):");
    if (!amount || isNaN(amount) || amount <= 0) {
      return alert("Please enter a valid amount.");
    }

    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(
        "/deposit/",
        { amount },
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (res.data.message === "Deposit successful") {
        alert("Deposit successful ✅");
        setBalance(Number(res.data.new_balance));
      } else {
        alert("Deposit failed ❌");
      }
    } catch (err) {
      console.error("Deposit error:", err);
      alert(err.response?.data?.error || "Deposit failed ❌");
    }
  };

  const handleWithdraw = () => {
    alert("Withdraw feature coming soon!");
  };

  const handleTransfer = async () => {
    const recipient = prompt("Enter recipient username:");
    const amount = prompt("Enter amount to send (KES):");
    if (!recipient || !amount || isNaN(amount) || amount <= 0) {
      return alert("Please provide valid details.");
    }

    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(
        "/transfer/",
        { recipient, amount },
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      alert(res.data.message);
      setBalance(parseFloat(res.data.sender_balance));
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.error || "Transfer failed.");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  if (loading) return <p style={{ textAlign: "center" }}>Loading your wallet...</p>;

  return (
    <div style={styles.container}>
      <h2>Welcome, {user?.first_name || "User"} 👋</h2>
      <div style={styles.balanceCard}>
        <h3>Wallet Balance</h3>
        <p style={styles.balance}>KES {balance.toFixed(2)}</p>
      </div>

      <div style={styles.actions}>
        <button style={styles.button} onClick={handleDeposit}>Deposit</button>
        <button style={styles.button} onClick={handleWithdraw}>Withdraw</button>
        <button style={styles.button} onClick={handleTransfer}>Send Money</button>
      </div>

      <button onClick={handleLogout} style={styles.logout}>Logout</button>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: "500px",
    margin: "50px auto",
    textAlign: "center",
    backgroundColor: "#f9f9f9",
    padding: "30px",
    borderRadius: "12px",
    boxShadow: "0 4px 10px rgba(0,0,0,0.1)",
  },
  balanceCard: {
    backgroundColor: "#fff",
    padding: "20px",
    borderRadius: "10px",
    marginBottom: "20px",
    boxShadow: "0 2px 6px rgba(0,0,0,0.1)",
  },
  balance: {
    fontSize: "28px",
    color: "#008000",
    margin: "10px 0",
  },
  actions: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    marginBottom: "20px",
  },
  button: {
    padding: "10px",
    backgroundColor: "#007bff",
    color: "white",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
  },
  logout: {
    backgroundColor: "#dc3545",
    color: "#fff",
    padding: "10px 15px",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
  },
};

export default WalletHome;
