import React, { useEffect, useState } from "react";
import axios from "../api/axiosConfig";
import { useNavigate } from "react-router-dom";

axios.defaults.baseURL = "http://127.0.0.1:8000/api"; // Backend base URL

const WalletHome = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0.0);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch user + wallet + transactions
  useEffect(() => {
    const token = localStorage.getItem("access_token");
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
        setBalance(parseFloat(res.data.wallet_balance) || 0.0);
        setTransactions(res.data.transactions || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Profile fetch error:", err);
        localStorage.removeItem("token");
        navigate("/login");
      });
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  // ----- Deposit Handler -----
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
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.data.message === "Deposit successful") {
        alert("Deposit successful ✅");
        setBalance(parseFloat(res.data.new_balance));
        fetchTransactions(); // Refresh transactions after deposit
      } else {
        alert("Deposit failed ❌");
      }
    } catch (err) {
      console.error("Deposit error:", err);
      alert(err.response?.data?.error || "Deposit failed ❌");
    }
  };

  // Reusable function to refresh transactions
  const fetchTransactions = async () => {
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTransactions(res.data.transactions || []);
    } catch (err) {
      console.error("Transaction refresh error:", err);
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
        { headers: { Authorization: `Bearer ${token}` } }
      );

      alert(res.data.message);
      setBalance(parseFloat(res.data.sender_balance));
      fetchTransactions(); // Refresh after transfer
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.error || "Transfer failed.");
    }
  };

  if (loading) return <p style={{ textAlign: "center" }}>Loading your wallet...</p>;

  return (
    <div style={styles.container}>
      <h2>Welcome, {user?.username || "User"} 👋</h2>

      <div style={styles.balanceCard}>
        <h3>Wallet Balance</h3>
        <p style={styles.balance}>KES {balance.toFixed(2)}</p>
      </div>

      <div style={styles.actions}>
        <button style={styles.button} onClick={handleDeposit}>
          Deposit
        </button>
        <button style={styles.button} onClick={handleWithdraw}>
          Withdraw
        </button>
        <button style={styles.button} onClick={handleTransfer}>
          Send Money
        </button>
      </div>

      {/* Transaction History */}
      <div style={styles.transactions}>
        <h3>Transaction History</h3>
        {transactions.length === 0 ? (
          <p>No transactions yet.</p>
        ) : (
          <ul style={styles.transactionList}>
            {transactions.map((tx, index) => (
              <li key={index} style={styles.transactionItem}>
                <span>
                  {tx.transaction_type}: <strong>KES {tx.amount}</strong>
                </span>
                <br />
                <small>{tx.description}</small>
                <br />
                <small style={{ color: "#666" }}>{tx.timestamp}</small>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button onClick={handleLogout} style={styles.logout}>
        Logout
      </button>
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
  transactions: {
    backgroundColor: "#fff",
    padding: "20px",
    borderRadius: "10px",
    textAlign: "left",
  },
  transactionList: {
    listStyle: "none",
    padding: 0,
  },
  transactionItem: {
    borderBottom: "1px solid #eee",
    padding: "10px 0",
  },
};

export default WalletHome;
