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
        self.running = True
        self.id = None
        self.road_scroll = 0.0

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
                        self.id = msg["id"]
                        self.road_scroll = msg.get("road_scroll", 0.0)
                    elif msg["type"] == "state":
                        self.players = msg["players"]
                        self.road_scroll = msg.get("road_scroll", self.road_scroll)
            except:
                break

    def send_input(self, dx, dy):
        msg = json.dumps({"dx": dx, "dy": dy}) + "\n"
        try:
            self.sock.sendall(msg.encode())
        except:
            pass

class ScrollingRoad:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Road dimensions
        self.road_width = 400
        self.road_x = (screen_width - self.road_width) // 2
        
        # Lane marking dimensions
        self.lane_width = 10
        self.lane_height = 40
        self.lane_gap = 30
        
    def draw(self, screen, scroll_y):
        # Draw grass/sides
        screen.fill((34, 139, 34))  # Green grass
        
        # Draw road
        pygame.draw.rect(screen, (60, 60, 60), 
                        (self.road_x, 0, self.road_width, self.screen_height))
        
        # Draw road edges (white lines)
        pygame.draw.rect(screen, (255, 255, 255), 
                        (self.road_x, 0, 5, self.screen_height))
        pygame.draw.rect(screen, (255, 255, 255), 
                        (self.road_x + self.road_width - 5, 0, 5, self.screen_height))
        
        # Draw center lane markings (yellow dashed line)
        center_x = self.road_x + self.road_width // 2 - self.lane_width // 2
        
        # Calculate how many lane markings we need to draw
        y = -scroll_y
        while y < self.screen_height:
            if y + self.lane_height > 0:  # Only draw if visible
                pygame.draw.rect(screen, (255, 255, 0), 
                               (center_x, int(y), self.lane_width, self.lane_height))
            y += self.lane_height + self.lane_gap

# ---------------------- PYGAME LOOP ----------------------
pygame.init()
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Multiplayer Road Game")
clock = pygame.time.Clock()

client = Client()
road = ScrollingRoad(SCREEN_WIDTH, SCREEN_HEIGHT)

rooms = discover_rooms()
if rooms:
    print("Found rooms:", rooms)
    client.connect(rooms[0]["host"])   # auto-join first found
else:
    print("No rooms found. Starting offline mode.")

running = True
fps_font = pygame.font.Font(None, 30)

while running:
    dx = dy = 0
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]: dx = -5
    if keys[pygame.K_RIGHT]: dx = 5
    if keys[pygame.K_UP]: dy = -5
    if keys[pygame.K_DOWN]: dy = 5

    client.send_input(dx, dy)

    # Draw road background with server-synced scroll
    road.draw(screen, client.road_scroll)
    
    # Draw players on top of road
    for p in client.players:
        color = (0, 255, 0) if p["id"] == client.id else (255, 100, 100)
        pygame.draw.rect(screen, color, (p["x"], p["y"], 40, 40))
        
        # Draw player ID
        id_text = fps_font.render(p["id"], True, (255, 255, 255))
        screen.blit(id_text, (p["x"] + 5, p["y"] + 10))
    
    # Draw FPS counter
    fps = int(clock.get_fps())
    fps_text = fps_font.render(f"FPS: {fps}", True, (255, 255, 255))
    screen.blit(fps_text, (10, 10))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
client.running = False
