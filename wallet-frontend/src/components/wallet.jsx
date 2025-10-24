import React, { useEffect, useState } from "react";
import axios from "../api/axiosConfig"; // Ensure axios is correctly configured
import { useNavigate } from "react-router-dom"; // if using React Router

const WalletHome = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0.0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch user details (assuming token saved in localStorage)
    const token = localStorage.getItem("token");
    if (!token) {
      navigate("/login");
      return;
    }

    axios
      .get("/api/user/profile/", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      .then((res) => {
        setUser(res.data);
        setBalance(res.data.balance || 0.0); // mock data
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem("token");
        navigate("/login");
      });
  }, [navigate]);

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

// Deposit Handler
const handleDeposit = async () => {
  const amount = prompt("Enter deposit amount (KES):");
  if (!amount || isNaN(amount) || amount <= 0) {
    return alert("Please enter a valid amount.");
  }

  try {
    const token = localStorage.getItem("token");
    const res = await axios.post(
      "/api/deposit/",
      { amount },
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    alert(res.data.message);
    setBalance(parseFloat(res.data.new_balance));
  } catch (err) {
    console.error(err);
    alert(err.response?.data?.error || "Deposit failed.");
  }
};

// Withdraw Handler
const handleWithdraw = () => {
  alert("Withdraw feature coming soon!");
};

// Transfer Handler
const handleTransfer = async () => {
  const recipient = prompt("Enter recipient username:");
  const amount = prompt("Enter amount to send (KES):");
  if (!recipient || !amount || isNaN(amount) || amount <= 0) {
    return alert("Please provide valid details.");
  }

  try {
    const token = localStorage.getItem("token");
    const res = await axios.post(
      "/api/transfer/",
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
