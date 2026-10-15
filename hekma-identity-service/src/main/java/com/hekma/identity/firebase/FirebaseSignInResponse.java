package com.hekma.identity.firebase;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FirebaseSignInResponse {
    private String idToken;
    private String refreshToken;
    private Long expiresIn;
    private String firebaseUid;
    private String email;
}
