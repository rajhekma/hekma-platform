package com.hekma.identity.firebase;

import com.hekma.identity.domain.Role;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FirebaseUserDto {
    private String uid;
    private String email;
    private String displayName;
    private Role role;
}
