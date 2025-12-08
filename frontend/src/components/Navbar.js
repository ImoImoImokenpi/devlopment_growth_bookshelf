import { Link, useLocation } from "react-router-dom";

export default function Navbar() {
    const location = useLocation();
    const currentPath = location.pathname;

    const links = [
        { path: "/", label: "本棚空間" },
        { path: "/Search", label: "本を探す" },
    ];

    return (
        <nav
            style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                marginBottom: "20px",
                padding: "10px 20px",
                backgroundColor: "#f8f9fa",
                boxShadow: "0 4px 6px rgba(0,0,0,0.1)",
            }}
        >
            {links
                .filter((link) => link.path !== currentPath) // 現在ページ以外だけ表示
                .map((link) => (
                    <Link
                        key={link.path}
                        to={link.path}
                        style={{
                            textDecoration: "none",
                            padding: "8px 16px",
                            borderRadius: "8px",
                            backgroundColor: "#e9ecef",
                            color: "#495057",
                            fontWeight: "500",
                            transition: "all 0.2s",
                        }}
                        onMouseEnter={(e) => (e.target.style.backgroundColor = "#dee2e6")}
                        onMouseLeave={(e) => (e.target.style.backgroundColor = "#e9ecef")}
                    >
                        {link.label}
                    </Link>
                ))}
        </nav>
    );
}