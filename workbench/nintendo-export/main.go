package main

import (
	"context"
	"crypto/subtle"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	nintendo "github.com/robtme/nintendo-go"
	"html/template"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

const private = "private"

func save(name string, b []byte) error {
	if err := os.MkdirAll(private, 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(private, ".tmp-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if _, err = f.Write(b); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return os.Rename(f.Name(), filepath.Join(private, name))
}
func validateCallback(raw string, login *nintendo.LoginRequest) error {
	u, e := url.Parse(strings.TrimSpace(raw))
	if e != nil {
		return errors.New("invalid callback")
	}
	q, e := url.ParseQuery(u.Fragment)
	if e != nil {
		return errors.New("invalid fragment")
	}
	if u.Scheme != "npf5c38e31cd085304b" || u.Host != "auth" || q.Get("session_token_code") == "" || subtle.ConstantTimeCompare([]byte(q.Get("state")), []byte(login.State)) != 1 {
		return errors.New("callback does not match this sign-in")
	}
	return nil
}
func export(ctx context.Context, token string) (int, error) {
	c := nintendo.NewClient(nintendo.Config{SessionToken: token})
	h, e := c.GetPlayHistory(ctx)
	if e != nil {
		return 0, e
	}
	stamp := time.Now().UTC().Format("20060102T150405Z")
	payload := struct {
		FetchedAt string                `json:"fetched_at"`
		Source    string                `json:"source"`
		History   *nintendo.PlayHistory `json:"history"`
	}{time.Now().UTC().Format(time.RFC3339), "nintendo-go v0.1.1", h}
	b, e := json.MarshalIndent(payload, "", "  ")
	if e != nil {
		return 0, e
	}
	if e = save(stamp+"-play-history.json", b); e != nil {
		return 0, e
	}
	var s strings.Builder
	w := csv.NewWriter(&s)
	w.Write([]string{"title_id", "title", "platform", "total_minutes", "first_played", "last_played", "total_days"})
	for _, t := range h.Titles {
		w.Write([]string{t.TitleID, t.TitleName, t.System(), strconv.Itoa(t.TotalPlayedMins), t.FirstPlayedAt, t.LastPlayedAt, strconv.Itoa(t.TotalPlayedDays)})
	}
	w.Flush()
	if e = w.Error(); e != nil {
		return 0, e
	}
	if e = save(stamp+"-titles.csv", []byte(s.String())); e != nil {
		return 0, e
	}
	return len(h.Titles), nil
}

// Preserve same-origin browser POST Origin; keep external sign-in links noreferrer.
func allowedSubmission(r *http.Request) bool {
	return r.Method == http.MethodPost && r.Host == "127.0.0.1:8766" && r.Header.Get("Origin") == "http://127.0.0.1:8766"
}
func main() {
	if len(os.Args) > 1 && os.Args[1] == "export" {
		b, e := os.ReadFile(filepath.Join(private, "session-token"))
		if e != nil {
			fmt.Fprintln(os.Stderr, "No local token. Run login first.")
			os.Exit(1)
		}
		n, e := export(context.Background(), strings.TrimSpace(string(b)))
		if e != nil {
			fmt.Fprintln(os.Stderr, "Export failed; no credentials printed. Reauthorize if expired.")
			os.Exit(1)
		}
		fmt.Printf("Exported %d titles to private JSON/CSV.\n", n)
		return
	}
	login, e := nintendo.NewLoginRequest()
	if e != nil {
		panic("Cannot create sign-in")
	}
	var mu sync.Mutex
	used := false
	page := template.Must(template.New("p").Parse(`<!doctype html><meta charset="utf-8"><title>Nintendo 本机只读导出</title><style>body{max-width:740px;margin:60px auto;font:18px system-ui;line-height:1.7}textarea{width:100%;height:100px}button,a{padding:10px}</style><h1>Nintendo 本机只读导出</h1><p>工具：nintendo-go v0.1.1。仅导出游玩记录，不写入 Yamtrack。</p><ol><li><a href="{{.URL}}" target="_blank" rel="noreferrer">打开 Nintendo 官方登录</a>，完成登录和验证。</li><li>在“选择此用户 / Select this person”按钮上右键，复制链接地址（npf…://auth#…）。不要把它发到聊天。</li><li>粘贴到下方本机输入框，点击保存并导出。</li></ol><form method="POST" action="/complete"><input type="hidden" name="nonce" value="{{.State}}"><textarea name="callback" autocomplete="off" spellcheck="false" required placeholder="仅在本机粘贴 Nintendo 回调链接"></textarea><br><button>保存并只读导出</button></form><p>会话凭证仅存本机 private/session-token，权限600。导出 JSON/CSV 留在 private/，不提交 Git。服务仅监听127.0.0.1。</p>`))
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Referrer-Policy", "same-origin")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
		if r.Host != "127.0.0.1:8766" {
			http.Error(w, "Invalid host", 403)
			return
		}
		if r.URL.Path != "/" || r.Method != "GET" {
			http.NotFound(w, r)
			return
		}
		page.Execute(w, login)
	})
	mux.HandleFunc("/complete", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		if !allowedSubmission(r) {
			http.Error(w, "提交来源验证失败，尚未交换授权。请重新打开 http://127.0.0.1:8766 首页后提交。", 403)
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 16384)
		if r.ParseForm() != nil || subtle.ConstantTimeCompare([]byte(r.FormValue("nonce")), []byte(login.State)) != 1 {
			http.Error(w, "Invalid form", 403)
			return
		}
		mu.Lock()
		defer mu.Unlock()
		if used {
			http.Error(w, "This login has already been used; restart for a new login.", 409)
			return
		}
		raw := r.FormValue("callback")
		if validateCallback(raw, login) != nil {
			http.Error(w, "Link does not match this login. Copy the full Select this person link from the login opened here.", 400)
			return
		}
		used = true
		c := nintendo.NewClient(nintendo.Config{})
		token, err := c.ExchangeCallback(r.Context(), raw, login.CodeVerifier)
		if err != nil {
			http.Error(w, "Authorization failed. No credentials were printed. Restart for a fresh login.", 502)
			return
		}
		if err = save("session-token", []byte(token)); err != nil {
			http.Error(w, "Could not save token locally.", 500)
			return
		}
		n, err := export(r.Context(), token)
		if err != nil {
			http.Error(w, "Token saved locally, but export failed. No credentials printed. Agent can retry the read-only export.", 502)
			return
		}
		fmt.Printf("Export complete: %d titles.\n", n)
		fmt.Fprintf(w, "Saved locally. Exported %d titles to private JSON/CSV. You can return to Codex. No Yamtrack data changed.", n)
	})
	fmt.Println("Nintendo local intake ready at http://127.0.0.1:8766")
	srv := &http.Server{Addr: "127.0.0.1:8766", Handler: mux, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 90 * time.Second}
	if srv.ListenAndServe() != http.ErrServerClosed {
		os.Exit(1)
	}
}
