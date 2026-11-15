package main

import (
	nintendo "github.com/robtme/nintendo-go"
	"net/http/httptest"
	"testing"
)

func TestCallbackBinding(t *testing.T) {
	l := &nintendo.LoginRequest{State: "expected"}
	for _, s := range []string{"https://evil.test/#state=expected&session_token_code=x", "npf5c38e31cd085304b://auth#state=wrong&session_token_code=x", "npf5c38e31cd085304b://auth#state=expected"} {
		if validateCallback(s, l) == nil {
			t.Fatal("accepted invalid callback")
		}
	}
	if validateCallback("npf5c38e31cd085304b://auth#state=expected&session_token_code=x", l) != nil {
		t.Fatal("rejected valid callback shape")
	}
}

func TestSubmissionOrigin(t *testing.T) {
	for _, tc := range []struct {
		method, host, origin string
		want                 bool
	}{
		{"POST", "127.0.0.1:8766", "http://127.0.0.1:8766", true},
		{"POST", "127.0.0.1:8766", "null", false},
		{"POST", "127.0.0.1:8766", "", false},
		{"POST", "127.0.0.1:8766", "https://evil.example", false},
		{"POST", "evil.example", "http://127.0.0.1:8766", false},
		{"GET", "127.0.0.1:8766", "http://127.0.0.1:8766", false},
	} {
		r := httptest.NewRequest(tc.method, "http://"+tc.host+"/complete", nil)
		r.Header.Set("Origin", tc.origin)
		if allowedSubmission(r) != tc.want {
			t.Errorf("unexpected result for %+v", tc)
		}
	}
}
