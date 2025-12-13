import { useContext } from "react";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

const GraphView = () => {
    const { myBookshelf = [] } = useContext(MyBookshelfContext);
    const count = myBookshelf.length;

    const maxPerRow = count <= 5 ? count : 5;
    const rows = count <= 5 ? 1 : 2;

    return (
        <div
            style={{
                width: "100%",
                display: "flex",
                justifyContent: "center",
                marginTop: "24px",
            }}
        >
            <div
                style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${maxPerRow}, 90px)`,
                    gridTemplateRows: `repeat(${rows}, 130px)`,
                    gap: "16px",
                }}
            >
                {myBookshelf.map((b) => (
                    <img
                        key={b.book_id}
                        src={b.cover}
                        alt={b.title}
                        style={{
                            width: "90px",
                            height: "130px",
                            objectFit: "cover",
                            borderRadius: "6px",
                        }}
                    />
                ))}
            </div>
        </div>
    );
};

export default GraphView;
