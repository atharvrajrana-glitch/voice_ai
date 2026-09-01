import React from "react";
import { LogOut, Bell } from "lucide-react";

export default function Navbar({ patientName, onSignOut }) {
  const [notifications, setNotifications] = React.useState(0);

  // Add animation keyframes
  React.useEffect(() => {
    const style = document.createElement("style");
    style.textContent = `
      @keyframes logoFloat {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-6px); }
      }
      @keyframes logoGlow {
        0%, 100% { box-shadow: 0 0 10px rgba(124, 58, 237, 0.4), inset 0 0 10px rgba(124, 58, 237, 0.1); }
        50% { box-shadow: 0 0 20px rgba(124, 58, 237, 0.6), inset 0 0 15px rgba(124, 58, 237, 0.2); }
      }
      .navbar-logo {
        animation: logoFloat 3s ease-in-out infinite, logoGlow 3s ease-in-out infinite;
      }
    `;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);

  return (
    <nav
      style={{
        position: "fixed",
        top: "16px",
        left: "50%",
        transform: "translateX(-50%)",
        width: "calc(100% - 32px)",
        maxWidth: "1200px",
        zIndex: 30,
        height: "60px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        boxSizing: "border-box",
        borderRadius: "20px",
        background: "rgba(26, 22, 34, 0.7)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(124, 58, 237, 0.2)",
        boxShadow: "0 8px 32px rgba(124, 58, 237, 0.1)",
        fontFamily: "Inter, sans-serif",
      }}
    >
      {/* Left side - Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div
          className="navbar-logo"
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "12px",
            background: "linear-gradient(135deg, #7C3AED, #A78BFA)",
            display: "grid",
            placeItems: "center",
            color: "#fff",
            fontWeight: "bold",
            fontSize: "18px",
          }}
        >
          M
        </div>
        <span
          style={{
            color: "#E4D5F5",
            fontFamily: "Georgia, serif",
            fontSize: "20px",
            fontWeight: 500,
          }}
        >
          MedClear
        </span>
      </div>

      {/* Center - Patient Info */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          color: "#C4B5FD",
          fontSize: "14px",
        }}
      >
        <div
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: "#10B981",
            boxShadow: "0 0 8px rgba(16, 185, 129, 0.6)",
          }}
        />
        <span>Connected</span>
      </div>

      {/* Right side - Bell, User & Sign Out */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            {/* User Profile */}
        {patientName && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "6px 12px",
              borderRadius: "12px",
              background: "rgba(124, 58, 237, 0.1)",
              border: "1px solid rgba(124, 58, 237, 0.2)",
            }}
          >
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                background: "linear-gradient(135deg, #7C3AED, #6C3FA3)",
                display: "grid",
                placeItems: "center",
                color: "#fff",
                fontSize: "14px",
                fontWeight: "600",
              }}
            >
              {patientName.charAt(0).toUpperCase()}
            </div>
            <span style={{ color: "#E4D5F5", fontSize: "13px", fontWeight: 500 }}>
              {patientName.split(" ")[0]}
            </span>
          </div>
        )}

        {/* Sign Out Button */}
        <button
          onClick={onSignOut}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            border: "1px solid rgba(167, 139, 250, 0.3)",
            borderRadius: "10px",
            padding: "8px 12px",
            background: "rgba(124, 58, 237, 0.15)",
            color: "#A78BFA",
            cursor: "pointer",
            font: "500 12px Inter, sans-serif",
            transition: "all 0.3s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(124, 58, 237, 0.25)";
            e.currentTarget.style.borderColor = "rgba(167, 139, 250, 0.5)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(124, 58, 237, 0.15)";
            e.currentTarget.style.borderColor = "rgba(167, 139, 250, 0.3)";
          }}
        >
          <LogOut size={14} />
          Sign out
        </button>
      </div>
    </nav>
  );
}
