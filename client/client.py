import socket
import threading
import json
import pygame
import time

DISCOVERY_PORT = 50001
TCP_PORT = 50000

# Discover rooms
def discover_rooms(timeout=1.5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)

    found = []
    start = time.time()

    while time.time() - start < timeout:
        sock.sendto(b"DISCOVER_ROOM", ("<broadcast>", DISCOVERY_PORT))
        try:
            data, addr = sock.recvfrom(1024)
            info = json.loads(data.decode())
            found.append(info)
        except:
            pass

    return found

class Client:
    def __init__(self):
        self.sock = None
        self.players = []
        self.obstacles = []
        self.game_active = True
        self.game_ended = False
        self.time_remaining = 0
        self.winner = None
        self.winner_score = 0
        self.running = True
        self.my_id = None

    def connect(self, host):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, TCP_PORT))
        threading.Thread(target=self.recv_loop, daemon=True).start()

    def recv_loop(self):
        buf = b""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line.decode())
                    
                    if msg["type"] == "welcome":
                        self.my_id = msg["id"]
                        print(f"Connected as {self.my_id}")
                    elif msg["type"] == "state":
                        self.players = msg["players"]
                        self.obstacles = msg["obstacles"]
                        self.game_active = msg.get("game_active", True)
                        self.game_ended = msg.get("game_ended", False)
                        self.time_remaining = msg.get("time_remaining", 0)
                        
                        if self.game_ended:
                            self.winner = msg.get("winner")
                            self.winner_score = msg.get("winner_score", 0)
            except:
                break

    def send_input(self, dx, dy):
        msg = json.dumps({"dx": dx, "dy": dy}) + "\n"
        try:
            self.sock.sendall(msg.encode())
        except:
            pass

    def get_my_player(self):
        for p in self.players:
            if p["id"] == self.my_id:
                return p
        return None

# ---------------------- PYGAME LOOP ----------------------
pygame.init()
screen = pygame.display.set_mode((1000, 700))
pygame.display.set_caption("Obstacle Dodge Game")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)
small_font = pygame.font.Font(None, 24)

client = Client()

# Connect to server
print("Searching for rooms...")
rooms = discover_rooms()
if rooms:
    print("Found rooms:", rooms)
    client.connect(rooms[0]["host"])
else:
    print("No rooms found. Starting anyway...")

running = True
while running:
    dx = dy = 0
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                running = False

    # Get input
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]: dx = -5
    if keys[pygame.K_RIGHT]: dx = 5
    if keys[pygame.K_UP]: dy = -5
    if keys[pygame.K_DOWN]: dy = 5

    client.send_input(dx, dy)

    # Draw
    screen.fill((20, 20, 30))
    
    # Draw grid lines for visual reference
    for i in range(0, 1000, 100):
        pygame.draw.line(screen, (40, 40, 50), (i, 0), (i, 700), 1)
    for i in range(0, 700, 100):
        pygame.draw.line(screen, (40, 40, 50), (0, i), (1000, i), 1)
    
    # Client renders obstacles
    for obs in client.obstacles:
        color_map = {
            "normal": (200, 50, 50),      # Red
            "fast": (255, 100, 0),        # Orange
            "bonus": (50, 200, 50),       # Green
            "penalty": (150, 50, 200)     # Purple
        }
        color = color_map.get(obs["type"], (200, 50, 50))
        
        pygame.draw.rect(screen, color, 
                        (obs["x"], obs["y"], obs["width"], obs["height"]))
        
        # Draw obstacle type indicator
        if obs["type"] == "bonus":
            pygame.draw.circle(screen, (100, 255, 100), 
                             (obs["x"] + obs["width"]//2, obs["y"] + obs["height"]//2), 
                             8)
        elif obs["type"] == "penalty":
            pygame.draw.line(screen, (255, 255, 255),
                           (obs["x"] + 10, obs["y"] + 10),
                           (obs["x"] + obs["width"] - 10, obs["y"] + obs["height"] - 10), 3)
            pygame.draw.line(screen, (255, 255, 255),
                           (obs["x"] + obs["width"] - 10, obs["y"] + 10),
                           (obs["x"] + 10, obs["y"] + obs["height"] - 10), 3)
    
    # Draw players
    my_player = client.get_my_player()
    for p in client.players:
        # Highlight own player
        if p["id"] == client.my_id:
            color = (0, 255, 255)  # Cyan for self
            thickness = 3
        else:
            color = (0, 255, 0)    # Green for others
            thickness = 0
        
        pygame.draw.rect(screen, color, 
                        (p["x"], p["y"], p["width"], p["height"]), 
                        thickness)
        if thickness == 0:
            pygame.draw.rect(screen, color, 
                            (p["x"], p["y"], p["width"], p["height"]))
        
        # Draw player ID
        id_text = small_font.render(p["id"], True, (255, 255, 255))
        screen.blit(id_text, (p["x"], p["y"] - 20))
    
    # Draw HUD
    if my_player:
        # Score
        score_text = font.render(f"Score: {my_player['score']}", True, (255, 255, 255))
        screen.blit(score_text, (10, 10))
        
        # Lives
        lives_text = font.render(f"Lives: {my_player['lives']}", True, (255, 50, 50))
        screen.blit(lives_text, (10, 50))
        
        # Lives hearts
        for i in range(my_player['lives']):
            pygame.draw.circle(screen, (255, 50, 50), (150 + i * 30, 65), 10)
    
    # Time remaining
    time_text = font.render(f"Time: {int(client.time_remaining)}s", True, (255, 255, 100))
    screen.blit(time_text, (850, 10))
    
    # Game status
    if not client.game_active and client.game_ended:
        # Semi-transparent overlay
        overlay = pygame.Surface((1000, 700))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))
        
        # Game over text
        game_over_text = font.render("GAME OVER!", True, (255, 255, 255))
        text_rect = game_over_text.get_rect(center=(500, 250))
        screen.blit(game_over_text, text_rect)
        
        # Winner announcement
        if client.winner:
            winner_text = font.render(f"Winner: {client.winner}", True, (255, 215, 0))
            winner_rect = winner_text.get_rect(center=(500, 320))
            screen.blit(winner_text, winner_rect)
            
            score_text = font.render(f"Score: {client.winner_score}", True, (255, 215, 0))
            score_rect = score_text.get_rect(center=(500, 370))
            screen.blit(score_text, score_rect)
        
        # Final scores
        y_offset = 420
        scores_title = small_font.render("Final Scores:", True, (200, 200, 200))
        screen.blit(scores_title, (400, y_offset))
        y_offset += 40
        
        sorted_players = sorted(client.players, key=lambda p: p["score"], reverse=True)
        for p in sorted_players:
            player_score = small_font.render(
                f"{p['id']}: {p['score']} points", 
                True, 
                (255, 255, 255)
            )
            screen.blit(player_score, (400, y_offset))
            y_offset += 30
    
    # Legend
    legend_y = 650
    legend_items = [
        ("Normal", (200, 50, 50)),
        ("Fast", (255, 100, 0)),
        ("Bonus", (50, 200, 50)),
        ("Penalty", (150, 50, 200))
    ]
    for i, (name, color) in enumerate(legend_items):
        x_pos = 10 + i * 150
        pygame.draw.rect(screen, color, (x_pos, legend_y, 20, 20))
        legend_text = small_font.render(name, True, (200, 200, 200))
        screen.blit(legend_text, (x_pos + 25, legend_y))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
client.running = False
