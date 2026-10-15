package com.hekma.identity.controller;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.dto.UpdateUserStatusRequest;
import com.hekma.identity.security.HekmaPrincipal;
import com.hekma.identity.service.UserManagementService;
import com.hekma.identity.service.UserQueryService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * GraphQL administrative API. Restricted to platform administrators (SYSTEM_ADMIN, ADMIN);
 * mutations additionally enforce the role hierarchy for the authenticated operator.
 */
@Controller
@Slf4j
@PreAuthorize("hasAnyRole('SYSTEM_ADMIN', 'ADMIN')")
public class UserGraphQlController {

    private final UserQueryService userQueryService;
    private final UserManagementService userManagementService;

    public UserGraphQlController(UserQueryService userQueryService, UserManagementService userManagementService) {
        this.userQueryService = userQueryService;
        this.userManagementService = userManagementService;
    }

    /**
     * Retrieves all users on the platform, or filters by role if provided.
     *
     * @param role optional role filter (SYSTEM_ADMIN, ADMIN, SPONSOR, SITE, PATIENT)
     * @return list of matching users
     */
    @QueryMapping
    public List<UserEntity> users(@Argument Role role) {
        log.info("GraphQL Query [users] invoked with role filter: {}", role);
        return userQueryService.getUsers(role);
    }

    /**
     * Retrieves a single user by database UUID.
     *
     * @param id user database UUID
     * @return UserEntity or null if not found
     */
    @QueryMapping
    public UserEntity userById(@Argument UUID id) {
        log.info("GraphQL Query [userById] invoked with id: {}", id);
        return userQueryService.getUserById(id).orElse(null);
    }

    /**
     * Retrieves a single user by email address.
     *
     * @param email user email address
     * @return UserEntity or null if not found
     */
    @QueryMapping
    public UserEntity userByEmail(@Argument String email) {
        log.info("GraphQL Query [userByEmail] invoked with email: {}", email);
        return userQueryService.getUserByEmail(email).orElse(null);
    }

    /**
     * Counts users, optionally filtered by role.
     *
     * @param role optional role filter
     * @return count of matching users
     */
    @QueryMapping
    public int userCount(@Argument Role role) {
        log.info("GraphQL Query [userCount] invoked with role: {}", role);
        return (int) userQueryService.getUserCount(role);
    }

    /**
     * Resolves the patientDetails field for User entities in batch, preventing N+1 queries.
     *
     * @param users list of parent User entities
     * @return map of UserEntity to PatientDetailEntity
     */
    @BatchMapping(typeName = "User", field = "patientDetails")
    public Map<UserEntity, PatientDetailEntity> patientDetails(List<UserEntity> users) {
        return userQueryService.getPatientDetailsForUsers(users);
    }

    /**
     * Updates active/inactive status of a target user, enforcing role hierarchy.
     */
    @MutationMapping
    public UserEntity updateUserActiveStatus(@Argument UUID userId, @Argument Boolean isActive,
                                             @AuthenticationPrincipal HekmaPrincipal caller) {
        log.info("GraphQL Mutation [updateUserActiveStatus] invoked for user: {} isActive: {} by operator: {}", userId, isActive, caller.userId());
        UpdateUserStatusRequest request = UpdateUserStatusRequest.builder()
                .isActive(isActive)
                .build();
        userManagementService.updateUserStatus(userId, request, caller.userId());
        return userQueryService.getUserById(userId).orElseThrow();
    }

    /**
     * Soft-deletes a user profile, enforcing role hierarchy.
     */
    @MutationMapping
    public boolean softDeleteUser(@Argument UUID userId, @AuthenticationPrincipal HekmaPrincipal caller) {
        log.info("GraphQL Mutation [softDeleteUser] invoked for user: {} by operator: {}", userId, caller.userId());
        userManagementService.softDeleteUser(userId, caller.userId());
        return true;
    }

    /**
     * Updates 2FA setting for a user profile.
     */
    @MutationMapping
    public UserEntity updateUserTwoFactor(@Argument UUID userId, @Argument Boolean twoFactorEnabled,
                                          @AuthenticationPrincipal HekmaPrincipal caller) {
        log.info("GraphQL Mutation [updateUserTwoFactor] invoked for user: {} twoFactorEnabled: {}", userId, twoFactorEnabled);
        userManagementService.updateTwoFactor(userId, twoFactorEnabled, caller);
        return userQueryService.getUserById(userId).orElseThrow();
    }
}
